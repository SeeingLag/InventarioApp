# -*- coding: utf-8 -*-
"""Pruebas de la autenticacion: DPAPI, Sesion, cabeceras y manejo del 401.

No necesita internet ni cuenta de Firebase: la red y DPAPI se sustituyen.
Uso:  python pruebas_auth.py [--gui]
"""
import io
import json
import os
import shutil
import sys
import tempfile
import time
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import inventario as inv

fallos = []
total = 0


def ok(nombre, condicion, detalle=""):
    global total
    total += 1
    if condicion:
        print("  OK    " + nombre)
    else:
        print("  FALLA " + nombre + ("  <- " + str(detalle) if detalle else ""))
        fallos.append(nombre)


def error_http(codigo, mensaje="x"):
    return urllib.error.HTTPError(
        "http://x", codigo, "x", {}, io.BytesIO(
            ('{"error":{"message":"%s"}}' % mensaje).encode("utf-8")))


class RespuestaFalsa:
    def __init__(self, texto):
        self.texto = texto

    def read(self):
        return self.texto.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class SesionStub:
    """Sesion de mentira: siempre devuelve un token valido."""

    def __init__(self, token="valido"):
        self.token_entregado = token
        self.cercada = False

    @property
    def activa(self):
        return True

    def token(self, forzar=False):
        return self.token_entregado

    def cerrar(self):
        self.cerrada = True


TMP = tempfile.mkdtemp(prefix="inv_pruebas_")
ruta_real = inv.ruta
inv.ruta = lambda nombre: os.path.join(TMP, nombre)
ARCHIVO_SESION = os.path.join(TMP, inv.RUTA_SESION)

dpapi_ok = inv._dpapi(b"prueba", cifrar=True) is not None
print("DPAPI disponible en este equipo: {0}".format(dpapi_ok))

print("1. Guardado de la sesion")
inv._guardar_sesion("refresh-de-prueba")
existe = os.path.exists(ARCHIVO_SESION)
if dpapi_ok:
    ok("se creo el archivo de sesion", existe)
    contenido = io.open(ARCHIVO_SESION, encoding="utf-8").read()
    ok("el archivo empieza con dpapi:", contenido.startswith("dpapi:"), contenido[:20])
    ok("el token NO esta en claro", "refresh-de-prueba" not in contenido)
    ok("se vuelve a leer bien", inv._leer_sesion() == "refresh-de-prueba",
       repr(inv._leer_sesion()))
else:
    ok("sin DPAPI no se escribe nada", not existe)
    ok("sin DPAPI no queda el token en disco", inv._leer_sesion() == "")

print("2. Borrar la sesion")
inv._guardar_sesion("")
ok("se borro el archivo", not os.path.exists(ARCHIVO_SESION))
ok("leer sin archivo devuelve vacio", inv._leer_sesion() == "")

print("3. Archivos damaged o inseguros")
with io.open(ARCHIVO_SESION, "w", encoding="utf-8") as f:
    f.write("dpapi:no-es-base64-valido!!")
ok("base64 roto devuelve vacio", inv._leer_sesion() == "")
ok("el archivo roto se borro", not os.path.exists(ARCHIVO_SESION))

with io.open(ARCHIVO_SESION, "w", encoding="utf-8") as f:
    f.write("")
ok("archivo vacio devuelve vacio", inv._leer_sesion() == "")

with io.open(ARCHIVO_SESION, "w", encoding="utf-8") as f:
    f.write("refresh-token-en-claro")
ok("no se lee un token en claro", inv._leer_sesion() == "")
ok("el archivo en claro se borro", not os.path.exists(ARCHIVO_SESION))

print("4. Sesion: sin sesion activa")
sesion = inv.Sesion()
ok("activa es False al empezar", sesion.activa is False)
ok("persistida es True al empezar", sesion.persistida is True)
try:
    sesion.token()
    ok("token() sin sesion avisa", False)
except RuntimeError as e:
    ok("token() sin sesion avisa", "sesion" in str(e).lower(), str(e))
try:
    sesion.entrar("", "clave")
    ok("entrar sin correo avisa", False)
except RuntimeError as e:
    ok("entrar sin correo avisa", "correo" in str(e).lower(), str(e))
try:
    sesion.entrar("no-es-correo", "clave")
    ok("entrar con correo malo avisa", False)
except RuntimeError as e:
    ok("entrar con correo malo avisa", "correo" in str(e).lower(), str(e))
try:
    sesion.entrar("a@b.com", "")
    ok("entrar sin contrasena avisa", False)
except RuntimeError as e:
    ok("entrar sin contrasena avisa", "contrasena" in str(e).lower(), str(e))


class SesionPost(inv.Sesion):
    """Sesion real pero sin red: _post devuelve lo que se le programe."""

    def _post(self, url, cuerpo):
        self.ultima_url = url
        self.ultimo_cuerpo = cuerpo
        return self.respuesta


print("5. Sesion: entrar")
s = SesionPost()
s.respuesta = {"idToken": "tok-123", "refreshToken": "ref-456",
               "email": "prueba@example.com", "expiresIn": 3600}
correo = s.entrar("  Prueba@Example.com  ", "clave")
ok("devuelve el correo de Firebase", correo == "prueba@example.com", correo)
ok("guarda el id token", s.id_token == "tok-123")
ok("guarda el refresh token", s.refresh_token == "ref-456")
ok("activa es True", s.activa is True)
ok("la caducidad es futura", s.caduca > time.time())
ok("usa signInWithPassword", "signInWithPassword" in s.ultima_url, s.ultima_url)
ok("la URL lleva la API key", inv.FIREBASE_API_KEY in s.ultima_url)
ok("recorta el correo", s.ultimo_cuerpo["email"] == "Prueba@Example.com",
   s.ultimo_cuerpo["email"])
contenido_persistido = ""
for nombre in (inv.RUTA_SESION, inv.RUTA_CONFIG):
    destino = os.path.join(TMP, nombre)
    if os.path.exists(destino):
        contenido_persistido += io.open(destino, encoding="utf-8").read()
ok("la peticion si manda la contrasena a Firebase", s.ultimo_cuerpo["password"] == "clave")
ok("la contrasena no se queda en disco", "clave" not in contenido_persistido,
   contenido_persistido[:80])
if dpapi_ok:
    ok("el refresh token quedo cifrado en disco",
       inv._leer_sesion() == "ref-456", repr(inv._leer_sesion()))
    ok("avisa que si se persistio", s.persistida is True)
else:
    ok("sin DPAPI el token no queda en disco", inv._leer_sesion() == "")
    ok("avisa que NO se persistio", s.persistida is False)

print("6. Sesion: renovar")
s2 = SesionPost()
s2.refresh_token = "ref-456"
s2.caduca = 0.0
s2.respuesta = {"id_token": "tok-nuevo", "expires_in": 3600}
ok("renueva cuando ya caduco", s2.token() == "tok-nuevo")
ok("usa el endpoint de refresh", s2.ultima_url.startswith(inv.SECURE_TOKEN_URL),
   s2.ultima_url)
ok("manda grant_type correcto",
   s2.ultimo_cuerpo["grant_type"] == "refresh_token", str(s2.ultimo_cuerpo))
ok("no vuelve a pedir si sigue vigente", s2.token() == "tok-nuevo")
s2.respuesta = {"id_token": "forzado", "expires_in": 3600}
ok("forzar=True renueva igual", s2.token(forzar=True) == "forzado")

print("7. Mensajes de error de Firebase")
trad = inv.Sesion._traducir_error
casos = [
    ("INVALID_LOGIN_CREDENTIALS", "incorrectos"),
    ("INVALID_PASSWORD", "incorrectos"),
    ("USER_DISABLED", "deshabilitada"),
    ("OPERATION_NOT_ALLOWED", "habilitado"),
    ("API_KEY_INVALID", "API key"),
    ("TOO_MANY_ATTEMPTS_TRY_LATER", "Demasiados"),
    ("NETWORK_REQUEST_FAILED", "conexion"),
]
for firebase, esperado in casos:
    texto = '{"error":{"message":"%s"}}' % firebase
    ok("error " + firebase, esperado in trad(texto, 400), trad(texto, 400))
ok("json roto no revienta", "codigo 500" in trad("no-json", 500))
ok("sin mensaje util da codigo", "codigo 418" in trad("{}", 418))

print("8. Sincronizador: cabecera Authorization")
peticiones = []


def urlopen_ok(peticion, timeout=None):
    peticiones.append(peticion)
    return RespuestaFalsa('{"SN1": {"S/N": "SN1"}}')


urlopen_real = inv.urllib.request.urlopen
inv.urllib.request.urlopen = urlopen_ok
sync = inv.Sincronizador("https://ejemplo.firebaseio.com", SesionStub())
resultado = sync._pedir("GET", "")
cab = peticiones[0].get_header("Authorization")
ok("la peticion lleva Authorization", cab == "Bearer valido", str(cab))
ok("va a inventario/productos",
   "/inventario/productos/.json" in peticiones[0].full_url,
   peticiones[0].full_url)
ok("devuelve el json", resultado == {"SN1": {"S/N": "SN1"}})
ok("no reintento si todo va bien", len(peticiones) == 1)
ok("con GET no manda cuerpo", peticiones[0].data is None)

print("9. Sincronizador: renueva y reintenta tras un 401")
peticiones2 = []


def urlopen_401(peticion, timeout=None):
    peticiones2.append(peticion.get_header("Authorization"))
    if len(peticiones2) == 1:
        raise error_http(401)
    return RespuestaFalsa('{"SN1": {"S/N": "SN1"}}')


inv.urllib.request.urlopen = urlopen_401
ses2 = SesionPost()
ses2.refresh_token = "ref-456"
ses2.id_token = "viejo"
ses2.caduca = time.time() + 9999
ses2.respuesta = {"id_token": "nuevo", "expires_in": 3600}
sync2 = inv.Sincronizador("https://ejemplo.firebaseio.com", ses2)
resultado2 = sync2._pedir("GET", "")
ok("reintenta una sola vez", len(peticiones2) == 2, str(peticiones2))
ok("el reintento usa el token nuevo", peticiones2[1] == "Bearer nuevo",
   str(peticiones2))
ok("el resultado llega igual", resultado2 == {"SN1": {"S/N": "SN1"}})

print("10. Sincronizador: 401ersistent")
peticiones3 = []


def urlopen_401_siempre(peticion, timeout=None):
    peticiones3.append(1)
    raise error_http(401)


inv.urllib.request.urlopen = urlopen_401_siempre
ses3 = SesionStub()
ses3.token_entregado = "malo"
ses3.cerrada = False
sync3 = inv.Sincronizador("https://ejemplo.firebaseio.com", ses3)
try:
    sync3._pedir("GET", "")
    ok("dos 401 avisan", False)
except RuntimeError as e:
    ok("dos 401 avisan que la sesion ya no vale", "ya no es valida" in str(e), str(e))
ok("no insiste mas de dos veces", len(peticiones3) == 2, str(len(peticiones3)))
ok("cierra la sesion caducada", ses3.cerrada is True)

print("11. Sincronizador: sin sesion")
inv.urllib.request.urlopen = urlopen_401_siempre
sync4 = inv.Sincronizador("https://ejemplo.firebaseio.com", None)
try:
    sync4._pedir("GET", "")
    ok("sin sesion avisa", False)
except RuntimeError as e:
    ok("sin sesion avisa del 401", "sin iniciar sesion" in str(e), str(e))

print("12. Sincronizador: reglas que bloquean")
inv.urllib.request.urlopen = lambda p, timeout=None: (_ for _ in ()).throw(
    error_http(403))
sync5 = inv.Sincronizador("https://ejemplo.firebaseio.com", SesionStub())
correcto, mensaje = sync5.probar()
ok("el 403 explica las reglas", not correcto and "auth != null" in mensaje, mensaje)

print("13. Sincronizador: otros errores")
inv.urllib.request.urlopen = lambda p, timeout=None: (_ for _ in ()).throw(
    error_http(404))
correcto, mensaje = inv.Sincronizador(
    "https://ejemplo.firebaseio.com", SesionStub()).probar()
ok("el 404 avisa de la URL", not correcto and "no existe" in mensaje, mensaje)


def urlopen_sin_red(peticion, timeout=None):
    raise urllib.error.URLError("sin red")


inv.urllib.request.urlopen = urlopen_sin_red
correcto, mensaje = inv.Sincronizador(
    "https://ejemplo.firebaseio.com", SesionStub()).probar()
ok("sin red avisa de la conexion", not correcto and "conexion" in mensaje, mensaje)

print("14. Sincronizador: URL vacia")
sync6 = inv.Sincronizador("", None)
ok("sin URL no esta activo", sync6.activo is False)
try:
    sync6._pedir("GET", "")
    ok("sin URL avisa", False)
except RuntimeError as e:
    ok("sin URL avisa", "URL" in str(e), str(e))

print("15. Configuracion (en carpeta temporal, no toca la tuya)")
inv.ruta = lambda nombre: os.path.join(TMP, nombre)
config = inv.leer_config()
ok("la config trae la URL de Firebase", config["sync_url"] == inv.FIREBASE_URL,
   config["sync_url"])
ok("la config trae la API key", config["api_key"] == inv.FIREBASE_API_KEY)
ok("la config no guarda contrasena",
   "password" not in json.dumps(config).lower())
ok("la config no guarda token", "token" not in json.dumps(config).lower())
inv.guardar_config(url="")
ok("se puede dejar vacio para modo local", inv.leer_config()["sync_url"] == "")
ok("vaciar no borra la API key",
   inv.leer_config()["api_key"] == inv.FIREBASE_API_KEY)
inv.guardar_config(url=inv.FIREBASE_URL)
inv.guardar_config(correo="alguien@example.com")
ok("guarda el correo para_no volver a escribirlo",
   inv.leer_config()["correo"] == "alguien@example.com")
inv.ruta = ruta_real
ok("el config.json real sigue con la URL de Firebase",
   inv.leer_config()["sync_url"] == inv.FIREBASE_URL, inv.leer_config()["sync_url"])

print("16. La ventana arranca y se cierra")
if "--gui" in sys.argv:
    try:
        ventana = inv.Ventana()
        ventana.update_idletasks()
        ventana.destroy()
        ok("la ventana se construye sin errores", True)
    except Exception as e:
        ok("la ventana se construye sin errores", False,
           "{0}: {1}".format(type(e).__name__, e))
else:
    print("  (omitida; pasale --gui si quieres probarla)")

inv.urllib.request.urlopen = urlopen_real
shutil.rmtree(TMP, ignore_errors=True)

print("=" * 58)
print("{0} pruebas, {1} fallos".format(total, len(fallos)))
for f in fallos:
    print("  - " + f)
sys.exit(1 if fallos else 0)