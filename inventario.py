"""Gestion de inventario de SSD - version de escritorio (Windows).

Solo usa la libreria estandar de Python: la aplicacion funciona sin internet
guardando los datos en inventario.json. La nube es opcional y se activa
iniciando sesion con Firebase Authentication (correo y contrasena); sin sesion
todo sigue funcionando en local.
"""

import base64
import calendar
import csv
import hashlib
import json
import os
import re
import sys
import time
import tkinter as tk
import urllib.error
import urllib.request
import zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta
from tkinter import filedialog, messagebox, simpledialog, ttk

APP_NOMBRE = "Inventario SSD"
RUTA_DATOS = "inventario.json"
RUTA_CONFIG = "config.json"
RUTA_RESPUALDO = "inventario_respaldo.json"
RUTA_SESION = "sesion.dat"

FIREBASE_URL = "https://inventarioapp-a80fe-default-rtdb.firebaseio.com"
FIREBASE_API_KEY = "AIzaSyBE18DcN8k9DZoQ7BLuwwJKwPmoYGdJRvQ"
IDENTITY_URL = "https://identitytoolkit.googleapis.com/v1"
SECURE_TOKEN_URL = "https://securetoken.googleapis.com/v1"

COLUMNAS = ["S/N", "Marca", "Modelo", "Tipo", "Capacidad", "Preciodecompra",
            "Estado", "Cliente", "PrecioVenta", "VenceGarantía",
            "FechaVenta", "FechaEntrada"]
COLS_FECHA = ["FechaVenta", "FechaEntrada"]
COLS_NUMERO = ["Preciodecompra", "PrecioVenta"]

TIPOS = ["M.2 NVMe", "SSD SATA"]
CAPACIDADES = ["120GB", "240GB", "256GB", "480GB", "512GB", "1TB", "2TB"]
NUEVA_MARCA = "NUEVA MARCA"
LIMITE_RESPALDOS = 5

# Orden de las pestanas y de las columnas de la tabla.
ETIQUETAS = {
    "S/N": "Serial",
    "Marca": "Marca",
    "Modelo": "Modelo",
    "Tipo": "Tipo",
    "Capacidad": "Capacidad",
    "Preciodecompra": "P. compra",
    "Estado": "Estado",
    "Cliente": "Cliente",
    "PrecioVenta": "P. venta",
    "VenceGarantía": "Vence garantia",
    "FechaVenta": "Fecha venta",
    "FechaEntrada": "Fecha entrada",
}
ANCHO_COLUMNAS = {
    "S/N": 170, "Marca": 100, "Modelo": 110, "Tipo": 95, "Capacidad": 95,
    "Preciodecompra": 85, "Estado": 95, "Cliente": 130, "PrecioVenta": 85,
    "VenceGarantía": 110, "FechaVenta": 105, "FechaEntrada": 105,
}


# --------------------------------------------------------------------------
# RUTAS Y UTILIDADES DE ARCHIVO
# --------------------------------------------------------------------------
def ruta_base():
    """Carpeta donde viven los datos: la del .exe, o la del script."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def ruta(nombre):
    return os.path.join(ruta_base(), nombre)


def escribir_json_atomico(destino, datos):
    """Escribe sin dejar el archivo a medias si el programa se cierra de golpe."""
    temporal = destino + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    os.replace(temporal, destino)


def _dpapi(datos, cifrar=True):
    """Cifra o descifra bytes con DPAPI de Windows (solo stdlib).

    Devuelve None si DPAPI no esta disponible, para que la app siga
    funcionando aunque el cifrado falle.
    """
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class _Blob(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_byte))]

        advapi = ctypes.WinDLL("Advapi32.dll")
        kernel = ctypes.WinDLL("Kernel32.dll")
        buffer = (ctypes.c_char * (len(datos) + 1)).from_buffer_copy(datos + b"\x00")
        origen = _Blob(len(datos), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
        destino = _Blob()
        entrada = ctypes.byref(origen)
        if cifrar:
            exito = advapi.CryptProtectData(entrada, "InventarioApp", None, None,
                                             None, 0x01, ctypes.byref(destino))
        else:
            exito = advapi.CryptUnprotectData(entrada, None, None, None, 0x01,
                                               ctypes.byref(destino))
        if not exito:
            return None
        try:
            return ctypes.string_at(destino.pbData, destino.cbData)
        finally:
            kernel.LocalFree(destino.pbData)
    except Exception:
        return None


def _borrar_sesion():
    try:
        os.remove(ruta(RUTA_SESION))
    except OSError:
        pass


def _leer_sesion():
    """Devuelve el refresh token guardado en disco, o "" si no hay.

    Solo se aceptan archivos cifrados con DPAPI: cualquier otra cosa se
    descarta, para no reutilizar un token que este en claro.
    """
    destino = ruta(RUTA_SESION)
    if not os.path.exists(destino):
        return ""
    try:
        with open(destino, "r", encoding="utf-8") as f:
            contenido = f.read().strip()
    except OSError:
        return ""
    if not contenido.startswith("dpapi:"):
        _borrar_sesion()
        return ""
    try:
        crudo = base64.b64decode(contenido[6:], validate=True)
    except (ValueError, TypeError):
        _borrar_sesion()
        return ""
    claro = _dpapi(crudo, cifrar=False)
    if not claro:
        _borrar_sesion()
        return ""
    try:
        return claro.decode("utf-8")
    except UnicodeDecodeError:
        _borrar_sesion()
        return ""


def _guardar_sesion(refresh_token):
    """Guarda el refresh token cifrado con DPAPI.

    Devuelve False si no se pudo cifrar: en ese caso NO se guarda nada y la
    sesion solo vive en memoria, para no dejar el token en claro en disco.
    """
    if not refresh_token:
        _borrar_sesion()
        return True
    protegido = _dpapi(refresh_token.encode("utf-8"), cifrar=True)
    if not protegido:
        _borrar_sesion()
        return False
    contenido = "dpapi:" + base64.b64encode(protegido).decode("ascii")
    with open(ruta(RUTA_SESION), "w", encoding="utf-8") as f:
        f.write(contenido)
    return True


def normalizar_sn(valor):
    if valor is None:
        return ""
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    return texto.strip().upper()


def clave_firebase(serial):
    """Firebase no admite . # $ [ ] / en las claves. Si hubo que cambiarlos
    se anade un hash para no perder ni mezclar seriales parecidos."""
    serial = normalizar_sn(serial)
    limpio = re.sub(r"[.#$\[\]/]", "_", serial)
    if limpio != serial:
        return "{0}_{1}".format(limpio, hashlib.sha1(serial.encode("utf-8")).hexdigest()[:8])
    return limpio


# --------------------------------------------------------------------------
# FECHAS
# --------------------------------------------------------------------------
def a_fecha(valor):
    """Convierte lo que llegue de un archivo o de Firebase a date, o None."""
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    texto = str(valor).strip()
    if texto == "" or texto.lower() in ("nan", "none", "nat"):
        return None
    if texto.upper() in ("N/A", "NA", "-"):
        return None
    for formato in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            continue
    try:
        numero = float(texto)
    except ValueError:
        return None
    try:
        return (datetime(1899, 12, 30) + timedelta(days=numero)).date()
    except (ValueError, OverflowError):
        return None


def a_iso(valor):
    f = a_fecha(valor)
    return f.isoformat() if f else ""


def formatear_fecha(valor):
    f = a_fecha(valor)
    return f.strftime("%d/%m/%Y") if f else ""


def hoy_iso():
    return date.today().isoformat()


# --------------------------------------------------------------------------
# LECTURA DE XLSX SOLO CON LA BIBLIOTECA ESTANDAR
# --------------------------------------------------------------------------
NS_XLSX = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def _columna_a_indice(letras):
    numero = 0
    for caracter in letras:
        numero = numero * 26 + (ord(caracter.upper()) - 64)
    return numero - 1


def _indice_a_columna(indice):
    letras = ""
    indice += 1
    while indice > 0:
        indice, resto = divmod(indice - 1, 26)
        letras = chr(65 + resto) + letras
    return letras


def leer_xlsx(ruta_xlsx):
    """Devuelve una lista de listas con el contenido de la primera hoja."""
    with zipfile.ZipFile(ruta_xlsx) as paquete:
        nombres = paquete.namelist()
        compartidas = []
        if "xl/sharedStrings.xml" in nombres:
            raiz = ET.fromstring(paquete.read("xl/sharedStrings.xml"))
            for nodo in raiz.findall(NS_XLSX + "si"):
                compartidas.append("".join(t.text or "" for t in nodo.iter(NS_XLSX + "t")))
        if "xl/workbook.xml" in nombres:
            raiz = ET.fromstring(paquete.read("xl/workbook.xml"))
            hojas = raiz.findall(NS_XLSX + "sheets/" + NS_XLSX + "sheet")
            objetivo = hojas[0].get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            relacion = None
            if "xl/_rels/workbook.xml.rels" in nombres:
                raiz_rel = ET.fromstring(paquete.read("xl/_rels/workbook.xml.rels"))
                for nodo in raiz_rel:
                    if nodo.get("Id") == objetivo:
                        relacion = nodo.get("Target")
                        break
            destino = None
            if relacion:
                relacion = relacion.lstrip("/")
                destino = relacion if relacion.startswith("xl/") else "xl/" + relacion
            if not destino or destino not in nombres:
                destino = "xl/worksheets/sheet1.xml"
        else:
            destino = "xl/worksheets/sheet1.xml"

        raiz = ET.fromstring(paquete.read(destino))
        datos = raiz.find(NS_XLSX + "sheetData")
        filas = []
        for fila in datos.findall(NS_XLSX + "row"):
            celdas = {}
            maximo = -1
            for celda in fila.findall(NS_XLSX + "c"):
                referencia = celda.get("r") or ""
                letras = "".join(c for c in referencia if c.isalpha())
                indice = _columna_a_indice(letras) if letras else len(celdas)
                maximo = max(maximo, indice)
                celdas[indice] = _valor_celda(celda, compartidas)
            filas.append([celdas.get(i, "") for i in range(maximo + 1)])
        return filas


def _valor_celda(celda, compartidas):
    tipo = celda.get("t")
    if tipo == "inlineStr":
        nodo = celda.find(NS_XLSX + "is")
        return "".join(t.text or "" for t in nodo.iter(NS_XLSX + "t")) if nodo is not None else ""
    valor = celda.find(NS_XLSX + "v")
    if valor is None or valor.text is None:
        return ""
    if tipo == "s":
        indice = int(valor.text)
        return compartidas[indice] if 0 <= indice < len(compartidas) else ""
    return valor.text


# --------------------------------------------------------------------------
# ALMACEN LOCAL
# --------------------------------------------------------------------------
class Almacen:
    """Los datos viven en inventario.json. Firebase es solo una copia mas."""

    def __init__(self):
        self.registros = []

    # -- carga y guardado --------------------------------------------------
    def cargar(self):
        if not os.path.exists(ruta(RUTA_DATOS)):
            self.registros = []
            return
        with open(ruta(RUTA_DATOS), "r", encoding="utf-8") as f:
            bruto = json.load(f)
        lista = bruto.get("productos", []) if isinstance(bruto, dict) else bruto
        self.registros = [self.normalizar(r) for r in lista]
        self._ordenar()

    def guardar(self):
        cuerpo = {
            "version": 1,
            "actualizado": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "productos": self.registros,
        }
        escribir_json_atomico(ruta(RUTA_DATOS), cuerpo)

    def respaldo_local(self):
        """Copia de seguridad previa a cada escritura importante."""
        if not os.path.exists(ruta(RUTA_DATOS)):
            return
        with open(ruta(RUTA_DATOS), "r", encoding="utf-8") as f:
            contenido = f.read()
        marca = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        with open(ruta("inventario_respaldo_{0}.json".format(marca)), "w", encoding="utf-8") as f:
            f.write(contenido)
        self._limpiar_respaldos()

    def _limpiar_respaldos(self):
        archivos = [f for f in os.listdir(ruta_base())
                    if f.startswith("inventario_respaldo_") and f.endswith(".json")]
        archivos.sort(reverse=True)
        for viejo in archivos[LIMITE_RESPALDOS:]:
            try:
                os.remove(ruta(viejo))
            except OSError:
                pass

    # -- consultas ---------------------------------------------------------
    def _ordenar(self):
        self.registros.sort(key=lambda r: (r.get("Estado", "") != "Disponible", r.get("S/N", "")))

    def normalizar(self, registro):
        limpio = {}
        for col in COLUMNAS:
            valor = registro.get(col, "")
            if col in COLS_NUMERO:
                try:
                    valor = int(float(valor))
                except (TypeError, ValueError):
                    valor = 0
            elif col in COLS_FECHA:
                valor = a_iso(valor)
            elif col == "S/N":
                valor = normalizar_sn(valor)
            elif col == "VenceGarantía":
                # En el Excel original ven como serial de Excel ("46138.0").
                # Se guarda como ISO para poder ordenar y comparar fechas.
                valor = a_iso(valor)
            elif col in ("Marca", "Modelo"):
                valor = str(valor).strip().upper()
            elif valor is None:
                valor = ""
            elif not isinstance(valor, str):
                valor = str(valor)
            limpio[col] = valor
        limpio["Estado"] = limpio["Estado"] or "Disponible"
        limpio["Cliente"] = limpio["Cliente"] or "N/A"
        limpio["_mod"] = registro.get("_mod", "")
        return limpio

    def buscar(self, texto):
        texto = (texto or "").strip().upper()
        if not texto:
            return list(self.registros)
        campos = ["S/N", "Marca", "Modelo", "Cliente"]
        return [r for r in self.registros
                if any(texto in str(r.get(c, "")).upper() for c in campos)]

    def disponibles(self):
        return [r for r in self.registros if r.get("Estado") == "Disponible"]

    def por_serial(self, serial):
        serial = normalizar_sn(serial)
        for r in self.registros:
            if r["S/N"] == serial:
                return r
        return None

    def marcas(self):
        return sorted({r["Marca"] for r in self.registros if r.get("Marca")})

    def tocar(self, registro):
        registro["_mod"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # -- escrituras --------------------------------------------------------
    def agregar(self, datos):
        nuevo = self.normalizar(datos)
        self.tocar(nuevo)
        self.registros.append(nuevo)
        self._ordenar()

    def actualizar_serial(self, serial, cambios):
        registro = self.por_serial(serial)
        if registro is None:
            return False
        registro.update(cambios)
        self.tocar(registro)
        return True

    def eliminar(self, serial):
        serial = normalizar_sn(serial)
        self.registros = [r for r in self.registros if r["S/N"] != serial]
        self._ordenar()

    def contar(self):
        return (len(self.disponibles()), len([r for r in self.registros
                                              if r.get("Estado") == "Vendido"]))


# --------------------------------------------------------------------------
# SINCRONIZACION CON FIREBASE
# --------------------------------------------------------------------------
def encontrar_mapa(filas):
    """Ubica la fila de titulos y devuelve (indice, mapa col->posicion)."""
    indice_encabezado = None
    for i, fila in enumerate(filas[:10]):
        normalizadas = [normalizar_sn(c) for c in fila]
        if "S/N" in normalizadas and "MARCA" in normalizadas:
            indice_encabezado = i
            break
    if indice_encabezado is None:
        raise ValueError(
            "No se encontraron los titulos. La primera fila debe empezar por S/N y Marca.")
    encabezados = [normalizar_sn(c) for c in filas[indice_encabezado]]
    mapa = {}
    for col in COLUMNAS:
        objetivo = normalizar_sn(col)
        if objetivo in encabezados:
            mapa[col] = encabezados.index(objetivo)
    if "S/N" not in mapa or "Marca" not in mapa:
        raise ValueError("Al archivo le faltan las columnas S/N o Marca.")
    return indice_encabezado, mapa


def importar_filas(almacen, filas):
    """Vuelca las filas de un Excel al almacen. Devuelve (nuevos, actualizados).

    Nunca borra informacion que el Excel no tiene: si el producto ya existe en
    la app se conservan su FechaVenta, su FechaEntrada y su venta.
    """
    indice_encabezado, mapa = encontrar_mapa(filas)
    nuevos, actualizados = 0, 0
    for fila in filas[indice_encabezado + 1:]:
        if not fila:
            continue

        def valor(col, _fila=fila):
            indice = mapa.get(col, -1)
            return _fila[indice] if 0 <= indice < len(_fila) else ""

        serial = normalizar_sn(valor("S/N"))
        if not serial:
            continue
        datos = almacen.normalizar({col: valor(col) for col in COLUMNAS})
        datos["S/N"] = serial
        existente = almacen.por_serial(serial)
        if existente is None:
            almacen.agregar(datos)
            nuevos += 1
            continue
        # El Excel no trae las fechas que se registran en la app: no se pisan.
        for campo in ("FechaVenta", "FechaEntrada"):
            if not datos.get(campo):
                datos[campo] = existente.get(campo, "")
        if existente.get("Estado") == "Vendido":
            # La app ya tiene esta venta registrada: es la fuente de verdad y
            # un Excel viejo no puede deshacerla ni cambiarle el cliente.
            datos["Estado"] = "Vendido"
            datos["Cliente"] = existente.get("Cliente") or datos.get("Cliente")
            datos["PrecioVenta"] = existente.get("PrecioVenta") or datos.get("PrecioVenta")
            datos["FechaVenta"] = existente.get("FechaVenta", "")
        almacen.actualizar_serial(serial, datos)
        actualizados += 1
    almacen.guardar()
    return nuevos, actualizados


class Sesion:
    """Inicio de sesion con Firebase Authentication (correo y contrasena).

    Guarda el refresh token cifrado con DPAPI para no pedir la contrasena
    cada vez que se abre la app.
    """

    def __init__(self, api_key=FIREBASE_API_KEY):
        self.api_key = api_key
        self.correo = ""
        self.id_token = ""
        self.refresh_token = ""
        self.caduca = 0.0
        # False si el equipo no deja cifrar la sesion: habra que entrar cada vez.
        self.persistida = True

    @property
    def activa(self):
        return bool(self.id_token or self.refresh_token)

    def iniciar(self):
        """Carga el refresh token guardado. No toca la red."""
        self.refresh_token = _leer_sesion()
        return self.activa

    def cerrar(self):
        self.correo = ""
        self.id_token = ""
        self.refresh_token = ""
        self.caduca = 0.0
        _guardar_sesion("")

    def _post(self, url, cuerpo):
        peticion = urllib.request.Request(
            url, data=json.dumps(cuerpo).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(peticion, timeout=25) as respuesta:
                return json.loads(respuesta.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise RuntimeError(self._traducir_error(
                e.read().decode("utf-8", "replace"), e.code)) from None
        except urllib.error.URLError:
            raise RuntimeError("No hay conexion a internet.") from None
        except ValueError:
            raise RuntimeError("Firebase devolvio algo que no se entiende.") from None

    @staticmethod
    def _traducir_error(cuerpo, codigo):
        mensaje = ""
        try:
            mensaje = json.loads(cuerpo).get("error", {}).get("message", "")
        except (ValueError, AttributeError):
            pass
        if any(x in mensaje for x in ("INVALID_LOGIN_CREDENTIALS", "INVALID_PASSWORD",
                                      "EMAIL_NOT_FOUND", "INVALID_EMAIL")):
            return "Correo o contrasena incorrectos."
        if "USER_DISABLED" in mensaje:
            return "Esa cuenta esta deshabilitada."
        if "OPERATION_NOT_ALLOWED" in mensaje:
            return ("El metodo correo/contrasena no esta habilitado. "
                    "Activalo en Firebase > Authentication.")
        if "API_KEY_INVALID" in mensaje or "CONFIGURATION_NOT_FOUND" in mensaje:
            return "La API key de Firebase no es valida."
        if any(x in mensaje for x in ("TOO_MANY_ATTEMPTS", "QUOTA_EXCEEDED",
                                      "BLOCKING_FUNCTION")):
            return "Demasiados intentos. Espera unos minutos e intentalo de nuevo."
        if "NETWORK" in mensaje or "UNAVAILABLE" in mensaje:
            return "No hay conexion a internet."
        return "No se pudo iniciar sesion (codigo {0}).".format(codigo)

    def entrar(self, correo, contrasena):
        correo = (correo or "").strip()
        if not correo or "@" not in correo:
            raise RuntimeError("Escribe un correo valido.")
        if not contrasena:
            raise RuntimeError("Escribe la contrasena.")
        datos = self._post(
            "{0}/accounts:signInWithPassword?key={1}".format(IDENTITY_URL, self.api_key),
            {"email": correo, "password": contrasena, "returnSecureToken": True})
        self._adoptar(datos)
        self.persistida = _guardar_sesion(self.refresh_token)
        return self.correo

    def _adoptar(self, datos):
        self.id_token = datos.get("idToken", "")
        self.refresh_token = datos.get("refreshToken", self.refresh_token)
        self.correo = datos.get("email", self.correo)
        self.caduca = time.time() + max(60, int(datos.get("expiresIn", 3600)) - 120)

    def renovar(self):
        if not self.refresh_token:
            raise RuntimeError("No has iniciado sesion.")
        datos = self._post(
            "{0}/token?key={1}".format(SECURE_TOKEN_URL, self.api_key),
            {"grant_type": "refresh_token", "refresh_token": self.refresh_token})
        token = datos.get("id_token", "")
        if not token:
            raise RuntimeError("Firebase no devolvio un token nuevo.")
        self.id_token = token
        if datos.get("refresh_token"):
            self.refresh_token = datos["refresh_token"]
            self.persistida = _guardar_sesion(self.refresh_token)
        self.caduca = time.time() + max(60, int(datos.get("expires_in", 3600)) - 120)
        return self.id_token

    def token(self, forzar=False):
        """Devuelve un id token vigente, renovandolo si ya caduco."""
        if not self.id_token or forzar or time.time() >= self.caduca:
            return self.renovar()
        return self.id_token

    def expires_info(self):
        """Lee el token: devuelve (segundos que le quedan, correo) o None.

        Sirve para distinguir un token caducado de unas reglas que rechazan:
        si el token sigue vivo y Firebase lo rechaza, el problema son las
        reglas de seguridad.
        """
        if not self.id_token:
            return None
        partes = self.id_token.split(".")
        if len(partes) < 2:
            return None
        try:
            relleno = partes[1] + "=" * (-len(partes[1]) % 4)
            datos = json.loads(base64.urlsafe_b64decode(relleno).decode("utf-8"))
            exp = int(datos.get("exp", 0))
        except (ValueError, TypeError, AttributeError):
            return None
        return exp - int(time.time()), datos.get("email", self.correo)


class Sincronizador:
    """Un registro por escrito: dos dispositivos nunca se pisan entero."""

    RUTA_BASE = "inventario/productos"

    def __init__(self, url="", sesion=None):
        self.url = (url or "").rstrip("/")
        self.sesion = sesion

    @property
    def activo(self):
        return bool(self.url)

    def _pedir(self, metodo, camino, cuerpo=None, reintentar=True):
        if not self.activo:
            raise RuntimeError("No hay URL de sincronizacion configurada.")
        url = "{0}/{1}/{2}.json".format(self.url, self.RUTA_BASE, camino)
        cabeceras = {"Content-Type": "application/json"}
        if self.sesion is not None:
            # El ID token va en ?auth=, que es como Realtime Database lo
            # acepta. En la cabecera Authorization: Bearer lo trata como si
            # fuera un token OAuth de Google y lo rechaza con
            # "Unauthorized request.", sin llegar a mirar las reglas.
            url += "?auth=" + self.sesion.token(forzar=not reintentar)
        datos = json.dumps(cuerpo, ensure_ascii=False).encode("utf-8") if cuerpo is not None else None
        peticion = urllib.request.Request(url, data=datos, method=metodo,
                                          headers=cabeceras)
        try:
            with urllib.request.urlopen(peticion, timeout=25) as respuesta:
                texto = respuesta.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            # La respuesta de Firebase dice la causa exacta (por ejemplo
            # "Permission denied"), asi que se enseña en vez de adivinarse.
            try:
                nota = (e.read() or b"").decode("utf-8", "replace").strip()
            except Exception:
                nota = ""
            if len(nota) > 200:
                nota = nota[:200] + "..."
            if nota:
                nota = "\n\nRespondio Firebase: " + nota
            if e.code == 401:
                if self.sesion is not None and reintentar:
                    # Puede que el token caducara: se renueva y se reintenta.
                    return self._pedir(metodo, camino, cuerpo, reintentar=False)
                if self.sesion is None:
                    raise RuntimeError(
                        "Firebase rechazo la peticion porque no hay sesion "
                        "iniciada. Ve a Nube > Iniciar sesion..." + nota) from None
                # Ya se renovo y aun asi lo rechaza: no es una sesion caducada.
                # Se invalida el token pero se conserva el refresh token, para
                # no obligar a escribir la contrasena otra vez.
                info = self.sesion.expires_info()
                self.sesion.id_token = ""
                self.sesion.caduca = 0.0
                if info is None:
                    raise RuntimeError(
                        "Firebase no acepto tu sesion. Vuelve a iniciar sesion..."
                        + nota) from None
                if info[0] > 60:
                    # El texto de Firebase se agrega DESPUES del format: si se
                    # concatena antes, sus llaves se tomarian como campos.
                    mensaje = (
                        "Tu sesion esta bien (caduca en {0} minutos), pero "
                        "Firebase no deja leer ni escribir.\n\n"
                        "Casi siempre son las reglas de seguridad: la base esta "
                        "cerrada para todos. Publica unas que permitan "
                        "'auth != null' en inventario/productos.\n"
                        "Estan en el README, seccion Nube (Firebase)."
                    ).format(int(info[0] // 60))
                    raise RuntimeError(mensaje + nota) from None
                raise RuntimeError(
                    "Tu sesion caduco y no se pudo renovar. Vuelve a iniciar "
                    "sesion..." + nota) from None
            if e.code == 403:
                raise RuntimeError(
                    "Firebase no autorizo la operacion (403). Revisa los permisos "
                    "de tu usuario y las reglas de seguridad." + nota) from None
            if e.code == 404:
                raise RuntimeError(
                    "La base no existe en esa URL. Revisa la configuracion."
                    + nota) from None
            raise RuntimeError("Firebase respondio con error {0}.".format(e.code)
                               + nota) from None
        except urllib.error.URLError:
            raise RuntimeError("No se pudo alcanzar Firebase. Revisa tu conexion.") from None
        return json.loads(texto) if texto else None

    def descargar(self):
        remoto = self._pedir("GET", "")
        if not isinstance(remoto, dict):
            return 0
        for clave, valores in remoto.items():
            if not isinstance(valores, dict):
                continue
            if "S/N" not in valores:
                valores["S/N"] = clave.replace("_", "-")
            limpio = self.almacen.normalizar(valores)
            existente = self.almacen.por_serial(limpio["S/N"])
            if existente is None:
                self.almacen.registros.append(limpio)
            elif (limpio.get("_mod") or "") > (existente.get("_mod") or ""):
                existente.update(limpio)
        self.almacen._ordenar()
        return len(remoto)

    def subir(self, registros):
        enviados = 0
        for registro in registros:
            # Se incluye _mod para que al descargar se pueda resolver cual
            # version es mas nueva; sin el, los cambios nunca llegarian.
            cuerpo = {c: registro.get(c, "") for c in COLUMNAS}
            cuerpo["_mod"] = registro.get("_mod", "")
            self._pedir("PUT", clave_firebase(registro["S/N"]), cuerpo)
            enviados += 1
        return enviados

    def borrar(self, serial):
        self._pedir("DELETE", clave_firebase(serial))

    def probar(self):
        """Comprueba que la URL responde y que la sesion tiene acceso."""
        try:
            self._pedir("GET", "")
            return True, "Conexion correcta."
        except RuntimeError as e:
            return False, str(e)
        except Exception as e:
            return False, "Error inesperado: {0}".format(e)


def leer_config():
    """Configuracion local. Nunca contiene contrasenas ni tokens."""
    datos = {"sync_url": FIREBASE_URL, "api_key": FIREBASE_API_KEY, "correo": ""}
    if os.path.exists(ruta(RUTA_CONFIG)):
        try:
            with open(ruta(RUTA_CONFIG), "r", encoding="utf-8") as f:
                guardado = json.load(f)
            if isinstance(guardado, dict):
                for campo in ("sync_url", "api_key", "correo"):
                    if isinstance(guardado.get(campo), str):
                        datos[campo] = guardado[campo]
        except (ValueError, OSError):
            pass
    return datos


def guardar_config(url=None, api_key=None, correo=None):
    """Actualiza la configuracion. Solo recibe lo que se cambia."""
    datos = leer_config()
    if url is not None:
        datos["sync_url"] = url.strip()
    if api_key is not None:
        datos["api_key"] = api_key.strip()
    if correo is not None:
        datos["correo"] = correo.strip()
    escribir_json_atomico(ruta(RUTA_CONFIG), datos)
    return datos


# --------------------------------------------------------------------------
# SERIALES PEGADOS (PEGADORA O CAMARA)
# --------------------------------------------------------------------------
def sumar_meses(fecha, meses):
    """Suma meses calendario (12 meses = 1 ano exacto, no 360 dias)."""
    if not meses:
        return fecha
    total = fecha.month - 1 + int(meses)
    anio = fecha.year + total // 12
    mes = total % 12 + 1
    ultimo = calendar.monthrange(anio, mes)[1]
    return date(anio, mes, min(fecha.day, ultimo))


def a_entero(valor, defecto=0):
    """Convierte a entero tolerando $ , espacios y miles con punto o coma.

    "1.500.000" -> 1500000    "1.200,50" -> 1200    "abc" -> defecto
    """
    if isinstance(valor, bool):
        return defecto
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float):
        return int(valor)
    limpio = re.sub(r"[^\d.,\-]", "", str(valor or "").strip())
    if not limpio:
        return defecto
    decimal = re.search(r"[.,](\d{1,2})$", limpio)
    if decimal:
        entero = re.sub(r"[.,]", "", limpio[:decimal.start()])
    else:
        entero = re.sub(r"[.,]", "", limpio)
    try:
        return int(entero)
    except ValueError:
        return defecto


def limpiar_seriales(texto):
    """Convierte un texto pegado en una lista de seriales, sin danarlos.

    Acepta uno por linea o separados por coma, punto y coma o espacios, y
    quita la etiqueta inicial "S/N:" o "SN:" si viene. Nunca quita un "SN"
    que sea parte del serial, ni descarta seriales cortos.
    """
    if not texto:
        return []
    limpio = str(texto).replace("\u00a0", " ").replace("\r", "\n")
    # La etiqueta solo se quita cuando encabeza el token.
    limpio = re.sub(r"(?i)\b(?:s\s*/\s*n|sn)\s*:\s*", " ", limpio)
    partes = re.split(r"[,\s\n;]+", limpio)
    salida, vistos = [], set()
    for parte in partes:
        token = parte.strip().strip(".;:|'\"")
        # "46138.0" viene de Excel: el .0 solo se quita si es todo numero.
        if re.fullmatch(r"\d+\.0", token):
            token = token[:-2]
        if not token:
            continue
        token = normalizar_sn(token)
        if not token or token in vistos:
            continue
        vistos.add(token)
        salida.append(token)
    return salida


# --------------------------------------------------------------------------
# INTERFAZ GRAFICA
# --------------------------------------------------------------------------
class DialogoLogin(tk.Toplevel):
    """Pide correo y contrasena para entrar a Firebase."""

    def __init__(self, padre, correo_sugerido=""):
        super().__init__(padre)
        self.title("Iniciar sesion")
        self.resizable(False, False)
        self.transient(padre)
        self.correo = tk.StringVar(value=correo_sugerido)
        self.clave = tk.StringVar()
        self.ver = tk.BooleanVar(value=False)
        self.error = tk.StringVar()
        self.resultado = None
        self.padre = padre

        marco = ttk.Frame(self, padding=16)
        marco.pack(fill="both", expand=True)
        ttk.Label(marco, text="Correo").grid(row=0, column=0, sticky="w", pady=(0, 6))
        ttk.Entry(marco, textvariable=self.correo, width=34).grid(
            row=0, column=1, pady=(0, 6))
        ttk.Label(marco, text="Contrasena").grid(row=1, column=0, sticky="w", pady=(0, 6))
        self.entrada_clave = ttk.Entry(marco, textvariable=self.clave, width=34, show="*")
        self.entrada_clave.grid(row=1, column=1, pady=(0, 6))
        ttk.Checkbutton(marco, text="Mostrar contrasena", variable=self.ver,
                        command=self._al_mostrar).grid(row=2, column=1, sticky="w")
        ttk.Label(marco, textvariable=self.error, foreground="#b00",
                  wraplength=300, justify="left").grid(
            row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        botones = ttk.Frame(marco)
        botones.grid(row=4, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(botones, text="Entrar", command=self._aceptar).pack(side="right")
        ttk.Button(botones, text="Cancelar", command=self.destroy).pack(side="right", padx=6)

        self.bind("<Return>", lambda e: self._aceptar())
        self.bind("<Escape>", lambda e: self.destroy())
        self.entrada_clave.focus_set()
        self.grab_set()

    def _al_mostrar(self):
        self.entrada_clave.configure(show="" if self.ver.get() else "*")

    def _aceptar(self):
        self.error.set("Entrando...")
        self.update_idletasks()
        try:
            self.resultado = self.padre.sesion.entrar(
                self.correo.get(), self.clave.get())
        except RuntimeError as e:
            self.error.set(str(e))
            return
        self.destroy()


class Ventana(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NOMBRE)
        self.geometry("1180x740")
        self.minsize(940, 600)

        self.almacen = Almacen()
        self.almacen.cargar()
        config = leer_config()
        self.sesion = Sesion(config.get("api_key") or FIREBASE_API_KEY)
        self.sesion.iniciar()
        self.sync = Sincronizador(config.get("sync_url") or FIREBASE_URL, self.sesion)

        self.vars = {}
        self._construir_menu()
        self._construir_barra()
        self._construir_pestanas()
        self._refrescar_todo()

    # -- marco -------------------------------------------------------------
    def _construir_menu(self):
        barra = tk.Menu(self)
        menu_datos = tk.Menu(barra, tearoff=0)
        menu_datos.add_command(label="Importar desde Excel...", command=self.importar_excel)
        menu_datos.add_command(label="Exportar a CSV (Excel)...", command=self.exportar_csv)
        menu_datos.add_command(label="Guardar copia local ahora", command=self.respaldo_manual)
        menu_datos.add_separator()
        menu_datos.add_command(label="Salir", command=self.destroy)
        barra.add_cascade(label="Archivo", menu=menu_datos)

        menu_nube = tk.Menu(barra, tearoff=0)
        menu_nube.add_command(label="Iniciar sesion...", command=self.iniciar_sesion)
        menu_nube.add_command(label="Cerrar sesion", command=self.cerrar_sesion)
        menu_nube.add_separator()
        menu_nube.add_command(label="Configurar Firebase...", command=self.configurar_sync)
        menu_nube.add_command(label="Probar conexion", command=self.probar_sync)
        menu_nube.add_command(label="Sincronizar ahora", command=self.sincronizar_ahora)
        barra.add_cascade(label="Nube", menu=menu_nube)

        menu_ayuda = tk.Menu(barra, tearoff=0)
        menu_ayuda.add_command(label="Acerca de", command=self.acerca_de)
        barra.add_cascade(label="Ayuda", menu=menu_ayuda)
        self.config(menu=barra)

    def _construir_barra(self):
        marco = ttk.Frame(self, padding=(10, 8))
        marco.pack(fill="x")
        self.etiqueta_estado = ttk.Label(marco, text="", font=("Segoe UI", 10, "bold"))
        self.etiqueta_estado.pack(side="left")
        ttk.Button(marco, text="Sincronizar ahora", command=self.sincronizar_ahora).pack(side="right")
        ttk.Button(marco, text="Importar Excel", command=self.importar_excel).pack(side="right", padx=6)
        ttk.Button(marco, text="Exportar CSV", command=self.exportar_csv).pack(side="right")

        cuerpo = ttk.Frame(self, padding=(10, 0, 10, 10))
        cuerpo.pack(fill="both", expand=True)
        self.notebook = ttk.Notebook(cuerpo)
        self.notebook.pack(fill="both", expand=True)

    def _pestana(self, titulo):
        marco = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(marco, text=titulo)
        return marco

    def _construir_pestanas(self):
        self._pestana_inventario()
        self._pestana_entrada()
        self._pestana_venta()
        self._pestana_precios()
        self._pestana_garantia()
        self._pestana_eliminar()

    # -- 1. inventario -----------------------------------------------------
    def _pestana_inventario(self):
        marco = self._pestana("Inventario actual")
        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        self.m_disponible = ttk.Label(fila, text="En stock: 0", font=("Segoe UI", 11, "bold"))
        self.m_disponible.pack(side="left")
        self.m_vendidos = ttk.Label(fila, text="Vendidos: 0", font=("Segoe UI", 11, "bold"))
        self.m_vendidos.pack(side="left", padx=20)
        self.var_busqueda = tk.StringVar()
        entrada = ttk.Entry(fila, textvariable=self.var_busqueda, width=34)
        entrada.pack(side="right")
        entrada.bind("<Return>", lambda e: self.refrescar_tabla())
        ttk.Label(fila, text="Buscar serial, marca, modelo o cliente:").pack(side="right", padx=6)

        marco_tabla = ttk.Frame(marco)
        marco_tabla.pack(fill="both", expand=True, pady=10)
        self.tabla = ttk.Treeview(marco_tabla, columns=COLUMNAS, show="headings", selectmode="browse")
        for col in COLUMNAS:
            self.tabla.heading(col, text=ETIQUETAS[col])
            self.tabla.column(col, width=ANCHO_COLUMNAS[col], anchor="center",
                              stretch=(col in ("S/N", "Cliente")))
        vertical = ttk.Scrollbar(marco_tabla, orient="vertical", command=self.tabla.yview)
        horizontal = ttk.Scrollbar(marco_tabla, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        marco_tabla.rowconfigure(0, weight=1)
        marco_tabla.columnconfigure(0, weight=1)
        self.tabla.bind("<Double-1>", self._doble_clic_tabla)
        ttk.Label(marco, text="Doble clic en una fila la copia en Buscar garantia.").pack(anchor="w")

    def _doble_clic_tabla(self, _evento):
        seleccion = self.tabla.selection()
        if not seleccion:
            return
        valores = self.tabla.item(seleccion[0], "values")
        if not valores:
            return
        self.var_garantia.set(valores[0])
        self.notebook.select(self.frame_garantia)
        self.refrescar_garantia()

    # -- 2. registrar entrada ----------------------------------------------
    def _pestana_entrada(self):
        marco = self._pestana("Registrar entrada")
        izquierda = ttk.Frame(marco)
        izquierda.pack(side="left", fill="both", expand=True, padx=(0, 12))
        derecha = ttk.Frame(marco)
        derecha.pack(side="left", fill="both", expand=True)

        self.var_marca_sel = tk.StringVar(value=NUEVA_MARCA)
        ttk.Label(izquierda, text="Marca").pack(anchor="w")
        self.combo_marca = ttk.Combobox(izquierda, textvariable=self.var_marca_sel,
                                        state="readonly", width=34)
        self.combo_marca.pack(fill="x", pady=(0, 8))
        self.combo_marca.bind("<<ComboboxSelected>>", self._al_cambiar_marca)

        self.var_marca = tk.StringVar()
        ttk.Label(izquierda, text="Nombre de la marca (solo si es nueva)").pack(anchor="w")
        ttk.Entry(izquierda, textvariable=self.var_marca, width=36).pack(fill="x", pady=(0, 8))

        self.var_modelo = tk.StringVar()
        ttk.Label(izquierda, text="Modelo").pack(anchor="w")
        ttk.Entry(izquierda, textvariable=self.var_modelo, width=36).pack(fill="x", pady=(0, 8))

        self.var_tipo = tk.StringVar(value=TIPOS[0])
        ttk.Label(izquierda, text="Tipo").pack(anchor="w")
        ttk.Combobox(izquierda, textvariable=self.var_tipo, values=TIPOS,
                     state="readonly", width=34).pack(fill="x", pady=(0, 8))

        self.var_capacidad = tk.StringVar(value=CAPACIDADES[3])
        ttk.Label(derecha, text="Capacidad").pack(anchor="w")
        ttk.Combobox(derecha, textvariable=self.var_capacidad, values=CAPACIDADES,
                     state="readonly", width=34).pack(fill="x", pady=(0, 8))

        self.var_precio_c = tk.StringVar(value="0")
        ttk.Label(derecha, text="Precio de compra ($)").pack(anchor="w")
        ttk.Spinbox(derecha, from_=0, to=99999999, textvariable=self.var_precio_c,
                    width=34).pack(fill="x", pady=(0, 8))

        self.var_precio_v = tk.StringVar(value="0")
        ttk.Label(derecha, text="Precio de venta sugerido ($)").pack(anchor="w")
        ttk.Spinbox(derecha, from_=0, to=99999999, textvariable=self.var_precio_v,
                    width=34).pack(fill="x", pady=(0, 8))

        ttk.Label(marco, text="Pega los seriales (uno por linea o separados por comas)").pack(
            anchor="w", pady=(14, 0))
        self.text_seriales_entrada = tk.Text(marco, height=6, font=("Consolas", 10))
        self.text_seriales_entrada.pack(fill="both", expand=True, pady=(4, 8))

        pie = ttk.Frame(marco)
        pie.pack(fill="x")
        self.etiqueta_fecha_entrada = ttk.Label(pie, text="")
        self.etiqueta_fecha_entrada.pack(side="left")
        ttk.Button(pie, text="Registrar entrada", command=self.registrar_entrada).pack(side="right")

    def _al_cambiar_marca(self, _evento):
        if self.var_marca_sel.get() != NUEVA_MARCA:
            self.var_marca.set(self.var_marca_sel.get())

    # -- 3. registrar venta ------------------------------------------------
    def _pestana_venta(self):
        marco = self._pestana("Registrar venta")
        izquierda = ttk.Frame(marco)
        izquierda.pack(side="left", fill="both", expand=True, padx=(0, 12))
        derecha = ttk.Frame(marco)
        derecha.pack(side="left", fill="both", expand=True)

        ttk.Label(izquierda, text="1. Pega los seriales").pack(anchor="w")
        self.text_seriales_venta = tk.Text(izquierda, height=8, font=("Consolas", 10))
        self.text_seriales_venta.pack(fill="both", expand=True, pady=(4, 8))
        ttk.Button(izquierda, text="Verificar disponibilidad",
                   command=self.verificar_venta).pack(anchor="e")

        self.var_cliente = tk.StringVar(value="CLIENTE FINAL")
        ttk.Label(derecha, text="2. Nombre del cliente").pack(anchor="w")
        ttk.Entry(derecha, textvariable=self.var_cliente, width=36).pack(fill="x", pady=(0, 8))

        self.var_meses = tk.IntVar(value=12)
        ttk.Label(derecha, text="3. Meses de garantia").pack(anchor="w")
        ttk.Spinbox(derecha, from_=0, to=120, textvariable=self.var_meses,
                    width=34).pack(fill="x", pady=(0, 8))

        self.etiqueta_venta = ttk.Label(derecha, text="", wraplength=430, justify="left")
        self.etiqueta_venta.pack(anchor="w", pady=(0, 10))

        marco_precios = ttk.LabelFrame(derecha, text="Precios finales", padding=10)
        marco_precios.pack(fill="both", expand=True)
        self.scroll_precios = ttk.Scrollbar(marco_precios, orient="vertical")
        self.scroll_precios.pack(side="right", fill="y")
        self.marco_precios = ttk.Frame(marco_precios)
        self.marco_precios.pack(side="left", fill="both", expand=True)
        self.precios_venta = {}
        self.encontrados = []

        pie = ttk.Frame(marco)
        pie.pack(fill="x", pady=(10, 0))
        self.etiqueta_fecha_venta = ttk.Label(pie, text="")
        self.etiqueta_fecha_venta.pack(side="left")
        ttk.Button(pie, text="Confirmar venta", command=self.confirmar_venta).pack(side="right")

    # -- 4. actualizar precios ---------------------------------------------
    def _pestana_precios(self):
        marco = self._pestana("Actualizar precios")
        self.var_marca_precio = tk.StringVar()
        ttk.Label(marco, text="Marca").pack(anchor="w")
        self.combo_marca_precio = ttk.Combobox(marco, textvariable=self.var_marca_precio,
                                                state="readonly", width=40)
        self.combo_marca_precio.pack(fill="x", pady=(0, 10))
        self.combo_marca_precio.bind("<<ComboboxSelected>>", lambda e: self._llenar_precios())

        self.var_producto = tk.StringVar()
        ttk.Label(marco, text="Producto").pack(anchor="w")
        self.combo_producto = ttk.Combobox(marco, textvariable=self.var_producto,
                                            state="readonly", width=40)
        self.combo_producto.pack(fill="x", pady=(0, 10))
        self.combo_producto.bind("<<ComboboxSelected>>", lambda e: self._cargar_precios_actuales())

        self.var_precio_c2 = tk.StringVar(value="0")
        ttk.Label(marco, text="Nuevo precio de compra ($)").pack(anchor="w")
        ttk.Spinbox(marco, from_=0, to=99999999, textvariable=self.var_precio_c2,
                    width=40).pack(fill="x", pady=(0, 10))

        self.var_precio_v2 = tk.StringVar(value="0")
        ttk.Label(marco, text="Nuevo precio de venta ($)").pack(anchor="w")
        ttk.Spinbox(marco, from_=0, to=99999999, textvariable=self.var_precio_v2,
                    width=40).pack(fill="x", pady=(0, 10))

        ttk.Label(marco, text="Se aplica solo al stock Disponible.",
                  foreground="#a33").pack(anchor="w", pady=(0, 10))
        ttk.Button(marco, text="Aplicar a stock", command=self.aplicar_precios).pack(anchor="w")

    # -- 5. buscar garantia ------------------------------------------------
    def _pestana_garantia(self):
        marco = self._pestana("Buscar garantia")
        self.frame_garantia = marco
        self.var_garantia = tk.StringVar()
        self.etiqueta_garantia = ttk.Label(marco, text="", foreground="#555")
        self.etiqueta_garantia.pack(anchor="w", pady=(0, 6))

        fila = ttk.Frame(marco)
        fila.pack(fill="x")
        ttk.Label(fila, text="Serial o fecha (DD/MM/AAAA)").pack(side="left")
        entrada = ttk.Entry(fila, textvariable=self.var_garantia, width=24)
        entrada.pack(side="left", fill="x", padx=8)
        entrada.bind("<Return>", lambda e: self.refrescar_garantia())
        ttk.Button(fila, text="Buscar", command=self.refrescar_garantia).pack(side="left")
        ttk.Button(fila, text="Ver todas", command=self._ver_todas_garantias).pack(side="left", padx=6)

        self.tabla_garantia = ttk.Treeview(
            marco, columns=["sn", "marca", "modelo", "cap", "estado", "vence", "dias"],
            show="headings", height=14)
        for col, texto, ancho, ancla in [
                ("sn", "S/N", 170, "w"), ("marca", "Marca", 105, "w"),
                ("modelo", "Modelo", 115, "w"), ("cap", "Capacidad", 95, "w"),
                ("estado", "Estado", 100, "w"), ("vence", "Vence garantia", 120, "center"),
                ("dias", "Dias", 110, "center")]:
            self.tabla_garantia.heading(col, text=texto)
            self.tabla_garantia.column(col, width=ancho, anchor=ancla)
        self.tabla_garantia.pack(fill="both", expand=True, pady=12)

    # -- 6. eliminar -------------------------------------------------------
    def _pestana_eliminar(self):
        marco = self._pestana("Eliminar registros")
        ttk.Label(marco, text="Escribe el serial que quieres borrar.",
                  foreground="#a33").pack(anchor="w", pady=(0, 6))
        ttk.Label(marco, text="Sehara un respaldo automatico antes de borrar.").pack(anchor="w")
        self.var_eliminar = tk.StringVar()
        entrada = ttk.Entry(marco, textvariable=self.var_eliminar, width=40)
        entrada.pack(anchor="w", pady=10)
        ttk.Button(marco, text="Eliminar", command=self.eliminar_registro).pack(anchor="w")

    # -- refresco ----------------------------------------------------------
    def _refrescar_todo(self):
        self.refrescar_tabla()
        self.refrescar_listas()
        disponibles, vendidos = self.almacen.contar()
        self.m_disponible.configure(text="En stock: {0}".format(disponibles))
        self.m_vendidos.configure(text="Vendidos: {0}".format(vendidos))
        self.etiqueta_fecha_entrada.configure(
            text="Se registrara como fecha de entrada: {0}".format(formatear_fecha(hoy_iso())))
        self.etiqueta_fecha_venta.configure(
            text="Se registrara como fecha de venta: {0}".format(formatear_fecha(hoy_iso())))
        self.refrescar_estado()

    def refrescar_tabla(self):
        for item in self.tabla.get_children():
            self.tabla.delete(item)
        for registro in self.almacen.buscar(self.var_busqueda.get()):
            fila = []
            for col in COLUMNAS:
                valor = registro.get(col, "")
                fila.append(formatear_fecha(valor) if col in COLS_FECHA else valor)
            self.tabla.insert("", "end", values=fila)

    def refrescar_listas(self):
        marcas = self.almacen.marcas()
        valores = [NUEVA_MARCA] + marcas
        self.combo_marca.configure(values=valores)
        if self.var_marca_sel.get() not in valores:
            self.var_marca_sel.set(NUEVA_MARCA)
        self.combo_marca_precio.configure(values=marcas)
        if marcas and self.var_marca_precio.get() not in marcas:
            self.var_marca_precio.set(marcas[0])
        if marcas:
            self._llenar_precios()

    def refrescar_estado(self):
        total = len(self.almacen.registros)
        datos = "{0} productos".format(total)
        if not self.sync.activo:
            texto, color = "Solo local (sin nube)  |  " + datos, "#a33"
        elif self.sesion.activa:
            texto = "En la nube como {0}  |  {1}".format(
                self.sesion.correo or "tu cuenta", datos)
            color = "#1a7f37"
        else:
            texto, color = "Nube lista, sesion no iniciada  |  " + datos, "#b8860b"
        self.etiqueta_estado.configure(text=texto, foreground=color)

    # -- acciones ----------------------------------------------------------
    def registrar_entrada(self):
        marca = self.var_marca.get().strip().upper() if \
            self.var_marca_sel.get() == NUEVA_MARCA else self.var_marca_sel.get()
        if not marca:
            messagebox.showwarning("Falta la marca", "Elige una marca o escribe una nueva.")
            return
        texto = self.text_seriales_entrada.get("1.0", "end")
        seriales = limpiar_seriales(texto)
        if not seriales:
            messagebox.showwarning("Sin seriales", "Pega al menos un serial.")
            return
        existentes = {r["S/N"] for r in self.almacen.registros}
        nuevos = [s for s in seriales if s not in existentes]
        repetidos = len(seriales) - len(nuevos)
        if not nuevos:
            messagebox.showinfo("Nada nuevo",
                                "Todos esos seriales ya estan en el inventario.")
            return
        self.almacen.respaldo_local()
        for serial in nuevos:
            self.almacen.agregar({
                "S/N": serial, "Marca": marca,
                "Modelo": self.var_modelo.get().strip().upper(),
                "Tipo": self.var_tipo.get(), "Capacidad": self.var_capacidad.get(),
                "Preciodecompra": a_entero(self.var_precio_c.get()), "Estado": "Disponible",
                "Cliente": "N/A", "PrecioVenta": a_entero(self.var_precio_v.get()),
                "VenceGarantía": "N/A", "FechaVenta": "",
                "FechaEntrada": hoy_iso(),
            })
        self.almacen.guardar()
        self._tras_escribir("Registrados {0} discos".format(len(nuevos)), repetidos)
        self.text_seriales_entrada.delete("1.0", "end")

    def verificar_venta(self):
        for hijo in self.marco_precios.winfo_children():
            hijo.destroy()
        self.precios_venta = {}
        seriales = limpiar_seriales(self.text_seriales_venta.get("1.0", "end"))
        if not seriales:
            self.encontrados = []
            self.etiqueta_venta.configure(text="Pega al menos un serial.")
            return
        encontrados = [self.almacen.por_serial(s) for s in seriales]
        encontrados = [r for r in encontrados if r and r.get("Estado") == "Disponible"]
        no_disponibles = [s for s in seriales
                           if not (self.almacen.por_serial(s)
                                   and self.almacen.por_serial(s).get("Estado") == "Disponible")]
        self.encontrados = encontrados
        self.etiqueta_venta.configure(
            text="Disponibles: {0}    No disponibles: {1}".format(
                len(encontrados), ", ".join(no_disponibles) or "ninguno"))
        if not encontrados:
            return
        for registro in encontrados:
            fila = ttk.Frame(self.marco_precios)
            fila.pack(fill="x", pady=2)
            ttk.Label(fila, text="{0}  ({1})".format(registro["S/N"], registro["Marca"]),
                      width=34, anchor="w").pack(side="left")
            # StringVar (no IntVar) para que se pueda escribir con puntos o
            # comas de miles; la conversion la hace a_entero al confirmar.
            variable = tk.StringVar(value=str(a_entero(registro.get("PrecioVenta"))))
            ttk.Entry(fila, textvariable=variable, width=14).pack(side="left")
            ttk.Label(fila, text="$").pack(side="left", padx=4)
            entrada = ""
            if registro.get("FechaEntrada"):
                entrada = formatear_fecha(registro["FechaEntrada"])
            ttk.Label(fila, text="entrada {0}".format(entrada or "sin dato"),
                      foreground="#666").pack(side="left", padx=10)
            self.precios_venta[registro["S/N"]] = variable

    def confirmar_venta(self):
        if not self.encontrados:
            messagebox.showwarning("Nada seleccionado",
                                   "Primero pega los seriales y pulsa Verificar disponibilidad.")
            return
        cliente = self.var_cliente.get().strip()
        if not cliente:
            messagebox.showwarning("Falta el cliente", "Escribe el nombre del cliente.")
            return
        meses = self.var_meses.get() or 0
        vencimiento = sumar_meses(date.today(), meses).strftime("%Y-%m-%d")
        fecha_venta = hoy_iso()
        self.almacen.respaldo_local()
        for registro in list(self.encontrados):
            precio = self.precios_venta.get(registro["S/N"])
            self.almacen.actualizar_serial(registro["S/N"], {
                "Estado": "Vendido", "Cliente": cliente,
                "PrecioVenta": a_entero(precio.get(), registro.get("PrecioVenta"))
                if precio is not None else a_entero(registro.get("PrecioVenta")),
                "VenceGarantía": vencimiento, "FechaVenta": fecha_venta,
            })
        self.almacen.guardar()
        self.encontrados = []
        self.precios_venta = {}
        self.text_seriales_venta.delete("1.0", "end")
        self._tras_escribir("Vendido a {0}".format(cliente), 0)

    def _llenar_precios(self):
        marca = self.var_marca_precio.get()
        if not marca:
            return
        vistos = []
        for registro in self.almacen.registros:
            if registro.get("Marca") != marca:
                continue
            clave = "{0} ({1}) - {2}".format(registro.get("Modelo"), registro.get("Tipo"),
                                             registro.get("Capacidad"))
            if clave not in vistos:
                vistos.append(clave)
        self.var_producto.set("")
        self.combo_producto.configure(values=vistos)
        if vistos:
            self.var_producto.set(vistos[0])
            self._cargar_precios_actuales()

    def _cargar_precios_actuales(self):
        partes = self._partes_producto()
        if not partes:
            return
        marca, modelo, tipo, capacidad = partes
        for registro in self.almacen.registros:
            if (registro.get("Marca") == marca and registro.get("Modelo") == modelo
                    and registro.get("Tipo") == tipo
                    and registro.get("Capacidad") == capacidad):
                self.var_precio_c2.set(int(registro.get("Preciodecompra") or 0))
                self.var_precio_v2.set(int(registro.get("PrecioVenta") or 0))
                return

    def _partes_producto(self):
        marca = self.var_marca_precio.get()
        seleccion = self.var_producto.get()
        if not seleccion or "(" not in seleccion or ")" not in seleccion:
            return None
        modelo = seleccion.split(" (")[0]
        resto = seleccion.split("(", 1)[1].rsplit(")", 1)[0]
        if " - " not in resto:
            return None
        tipo, capacidad = resto.rsplit(" - ", 1)
        return marca, modelo, tipo, capacidad

    def aplicar_precios(self):
        partes = self._partes_producto()
        if not partes:
            messagebox.showwarning("Falta el producto", "Elige marca y producto.")
            return
        marca, modelo, tipo, capacidad = partes
        self.almacen.respaldo_local()
        compra, venta = a_entero(self.var_precio_c2.get()), a_entero(self.var_precio_v2.get())
        afectados = 0
        for registro in list(self.almacen.registros):
            if (registro.get("Marca") == marca and registro.get("Modelo") == modelo
                    and registro.get("Tipo") == tipo
                    and registro.get("Capacidad") == capacidad
                    and registro.get("Estado") == "Disponible"):
                self.almacen.actualizar_serial(registro["S/N"], {
                    "Preciodecompra": compra, "PrecioVenta": venta})
                afectados += 1
        if not afectados:
            messagebox.showinfo("Sin cambios", "No hay discos disponibles de ese producto.")
            return
        self.almacen.guardar()
        self._tras_escribir("Precios actualizados en {0} discos".format(afectados), 0)

    @staticmethod
    def _dias_para_vencer(fecha_iso):
        objetivo = a_fecha(fecha_iso)
        if objetivo is None:
            return None
        return (objetivo - date.today()).days

    def _pintar_garantias(self, registros, nota):
        for item in self.tabla_garantia.get_children():
            self.tabla_garantia.delete(item)
        for registro in registros:
            vence = registro.get("VenceGarantía", "")
            dias = self._dias_para_vencer(vence)
            if dias is None:
                texto_dias = "sin dato"
            elif dias < 0:
                texto_dias = "vencida hace {0}".format(abs(dias))
            elif dias == 0:
                texto_dias = "vence hoy"
            else:
                texto_dias = "faltan {0}".format(dias)
            self.tabla_garantia.insert("", "end", values=(
                registro.get("S/N", ""), registro.get("Marca", ""),
                registro.get("Modelo", ""), registro.get("Capacidad", ""),
                registro.get("Estado", ""),
                formatear_fecha(vence) or "sin dato", texto_dias))
        self.etiqueta_garantia.configure(text=nota)

    def _ver_todas_garantias(self):
        registros = [r for r in self.almacen.registros if r.get("VenceGarantía")]
        registros.sort(key=lambda r: r.get("VenceGarantía", ""))
        vencidas = sum(1 for r in registros
                       if (self._dias_para_vencer(r["VenceGarantía"]) or 0) < 0)
        self._pintar_garantias(
            registros, "{0} productos con garantia ({1} ya vencidas).".format(
                len(registros), vencidas))

    def refrescar_garantia(self):
        texto = (self.var_garantia.get() or "").strip()
        if not texto:
            self._ver_todas_garantias()
            return
        registro = self.almacen.por_serial(texto)
        if registro is not None:
            self._pintar_garantias([registro],
                                   "Serial {0}.".format(registro["S/N"]))
            return
        objetivo = a_fecha(texto)
        if objetivo is None:
            self._pintar_garantias(
                [], "No es un serial ni una fecha. Usa DD/MM/AAAA (ej. 26/04/2026).")
            return
        limite = objetivo.isoformat()
        coincidencias = [r for r in self.almacen.registros
                         if r.get("VenceGarantía") and r["VenceGarantía"] <= limite]
        coincidencias.sort(key=lambda r: r.get("VenceGarantía", ""))
        self._pintar_garantias(
            coincidencias,
            "{0} productos con garantia vencida a esa fecha.".format(len(coincidencias)))

    def eliminar_registro(self):
        serial = normalizar_sn(self.var_eliminar.get())
        if not serial:
            messagebox.showwarning("Falta el serial", "Escribe el serial a eliminar.")
            return
        registro = self.almacen.por_serial(serial)
        if registro is None:
            messagebox.showinfo("No encontrado", "Ese serial no esta en el inventario.")
            return
        if not messagebox.askyesno(
                "Confirmar borrado",
                "Se borrara {0} ({1}).\n\nSehara un respaldo automatico.\n\nContinuar?".format(
                    registro["S/N"], registro.get("Marca", ""))):
            return
        self.almacen.respaldo_local()
        self.almacen.eliminar(serial)
        self.almacen.guardar()
        if self.sync.activo:
            try:
                self.sync.borrar(serial)
            except Exception as e:
                messagebox.showwarning("Nube", "Borro en esta maquina pero no en la nube: {0}".format(e))
        self.var_eliminar.set("")
        self._tras_escribir("Eliminado {0}".format(serial), 0)

    # -- nube --------------------------------------------------------------
    def iniciar_sesion(self):
        if self.sesion.activa and self.sesion.id_token:
            messagebox.showinfo("Sesion activa", "Ya estas dentro como {0}.".format(
                self.sesion.correo or "tu cuenta"))
            return
        dialogo = DialogoLogin(self, leer_config().get("correo", ""))
        self.wait_window(dialogo)
        if dialogo.resultado:
            guardar_config(correo=dialogo.resultado)
            self.refrescar_estado()
            texto = ("Listo como {0}.\n\nYa puedes sincronizar desde el boton de arriba."
                     .format(dialogo.resultado))
            if not self.sesion.persistida:
                texto += ("\n\nOjo: este equipo no deja cifrar la sesion, asi que"
                          "\ntendras que volver a escribir la contrasena cada vez.")
            messagebox.showinfo("Sesion iniciada", texto)
        else:
            self.refrescar_estado()

    def cerrar_sesion(self):
        if not self.sesion.activa:
            messagebox.showinfo("Sesion", "No habia ninguna sesion iniciada.")
            return
        self.sesion.cerrar()
        guardar_config(correo="")
        self.refrescar_estado()
        messagebox.showinfo("Sesion cerrada",
                            "Se borro la sesion guardada en este equipo.\n"
                            "Tus datos locales no se tocaron.")

    def _pedir_login(self):
        """Si no hay sesion, la pide. Devuelve True si se puede seguir."""
        if self.sesion.activa:
            return True
        messagebox.showinfo(
            "Sesion necesaria",
            "Para sincronizar hay que iniciar sesion con tu cuenta de Firebase.\n\n"
            "Puedes seguir trabajando en local sin iniciar sesion.")
        self.iniciar_sesion()
        return self.sesion.activa

    def configurar_sync(self):
        actual = leer_config().get("sync_url", "")
        entrada = simpledialog.Dialog(
            self, "Configurar Firebase",
            text="Pega la URL de tu base de Firebase Realtime Database.\n"
                 "Dejalo vacio para trabajar solo en este equipo.",
            strings={"text": actual}).result
        if entrada is None:
            return
        self.sync = Sincronizador(entrada, self.sesion)
        guardar_config(url=entrada)
        if not self.sync.activo:
            messagebox.showinfo("Sin nube", "Se guardo vacio: la app quedo solo local.")
            self.refrescar_estado()
            return
        if not self._pedir_login():
            messagebox.showwarning(
                "Sin sesion",
                "La URL quedo guardada, pero hace falta iniciar sesion para usarla.")
            self.refrescar_estado()
            return
        correcto, mensaje = self.sync.probar()
        (messagebox.showinfo if correcto else messagebox.showerror)(
            "Configurar Firebase", mensaje)
        self.refrescar_estado()

    def probar_sync(self):
        if not self.sync.activo:
            messagebox.showinfo("Sin nube", "Configura una URL en Nube > Configurar Firebase.")
            return
        if not self._pedir_login():
            return
        correcto, mensaje = self.sync.probar()
        (messagebox.showinfo if correcto else messagebox.showerror)(
            "Prueba de conexion", mensaje)

    def sincronizar_ahora(self):
        if not self.sync.activo:
            messagebox.showinfo("Sin nube", "Configura una URL en Nube > Configurar Firebase.")
            return
        if not self._pedir_login():
            return
        try:
            self.sync.almacen = self.almacen
            recibidos = self.sync.descargar()
            enviados = self.sync.subir(self.almacen.registros)
            self.almacen.guardar()
        except Exception as e:
            messagebox.showerror("No se pudo sincronizar",
                                 "No se toco nada. Error: {0}".format(e))
            return
        self._refrescar_todo()
        messagebox.showinfo("Sincronizado",
                            "Recibidos: {0}    Enviados: {1}".format(recibidos, enviados))

    # -- importacion y exportacion ----------------------------------------
    def importar_excel(self):
        archivo = filedialog.askopenfilename(
            title="Elegir el archivo de Excel",
            filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")])
        if not archivo:
            return
        try:
            filas = leer_xlsx(archivo)
        except Exception as e:
            messagebox.showerror("No se pudo leer", "El archivo no es un .lsx valido: {0}".format(e))
            return
        if not filas:
            messagebox.showerror("Archivo vacio", "La hoja no tiene datos.")
            return
        self.almacen.respaldo_local()
        try:
            nuevos, actualizados = importar_filas(self.almacen, filas)
        except ValueError as e:
            messagebox.showerror("No se pudo importar", str(e))
            return
        self._refrescar_todo()
        messagebox.showinfo(
            "Importacion terminada",
            "Nuevos: {0}\nActualizados: {1}\nTotal en la app: {2}".format(
                nuevos, actualizados, len(self.almacen.registros)))

    def exportar_csv(self):
        archivo = filedialog.asksaveasfilename(
            title="Guardar como CSV", defaultextension=".csv",
            initialfile="inventario_{0}.csv".format(date.today().isoformat()),
            filetypes=[("CSV", "*.csv")])
        if not archivo:
            return
        with open(archivo, "w", newline="", encoding="utf-8-sig") as f:
            escritor = csv.writer(f)
            escritor.writerow([ETIQUETAS[c] for c in COLUMNAS])
            for registro in self.almacen.registros:
                escritor.writerow([formatear_fecha(registro.get(c, ""))
                                   if c in COLS_FECHA else registro.get(c, "")
                                   for c in COLUMNAS])
        messagebox.showinfo("Exportado", "Archivo guardado en:\n" + archivo)

    def respaldo_manual(self):
        self.almacen.respaldo_local()
        messagebox.showinfo("Respaldo", "Se guardo una copia local de seguridad.")

    def acerca_de(self):
        messagebox.showinfo("Acerca de", "{0} v1.0\n\nDatos en: {1}\n{2}".format(
            APP_NOMBRE, ruta(RUTA_DATOS),
            "Nube: " + (self.sync.url if self.sync.activo else "desactivada")))

    # -- comun -------------------------------------------------------------
    def _tras_escribir(self, mensaje, repetidos):
        texto = mensaje
        if repetidos:
            texto += "\n({0} serial(es) ya existian y se omitieron)".format(repetidos)
        # Sin sesion el dato se queda en local y sube la proxima sincronizacion.
        if self.sync.activo and self.sesion.activa:
            try:
                self.sync.almacen = self.almacen
                self.sync.subir(self.almacen.registros)
                self.almacen.guardar()
            except Exception as e:
                messagebox.showwarning(
                    "Guardado solo en esta maquina",
                    "{0}\n\nSe guardo aqui pero no se pudo subir a la nube: {1}".format(
                        mensaje, e))
                self._refrescar_todo()
                return
        elif self.sync.activo:
            texto += "\n\nQuedo solo en este equipo. Sincroniza cuando inicies sesion."
        self._refrescar_todo()
        messagebox.showinfo("Listo", texto)


if __name__ == "__main__":
    Ventana().mainloop()
