# InventarioApp

Aplicacion de escritorio (Windows) para inventario de una tienda de componentes
de computador. Funciona **sin internet**: guarda todo en `inventario.json` junto
al programa y, si se configura, sincroniza con Firebase.

Esta app es independiente del proyecto Alcancia y no comparte nada con el.

## Como se usa

Ejecuta `InventarioApp.exe` (o `python inventario.py` si tienes Python).

Las seis pantallas son:

| Pantalla | Para que sirve |
| --- | --- |
| **Inventario actual** | Ver y buscar todo. Muestra serial, marca, modelo, tipo, capacidad, estado, cliente, precios, garantia y fechas. |
| **Registrar entrada** | Pega varios seriales de una vez y los da de alta con marca, modelo, tipo, capacidad y precios. |
| **Registrar venta** | Pega los seriales, verifica que esten disponibles, pone cliente, meses de garantia y precio final de cada uno. |
| **Actualizar precios** | Cambia compra y venta de un modelo por completo, solo al stock Disponible. |
| **Buscar garantia** | Busca por serial o por fecha, y dice quantos dias faltan (o quantos hace que vencio). |
| **Eliminar registros** | Borra un serial, con confirmacion y respaldo automatico. |

## Fechas

- Se guardan en formato `AAAA-MM-DD` y se muestran como `DD/MM/AAAA`.
- Los productos que ya tenias **no reciben fecha inventada**: quedan vacias.
- Al registrar una entrada se anota sola la `FechaEntrada` (hoy).
- Al confirmar una venta se anota sola la `FechaVenta` (hoy).

## Tus datos

- Los datos viven en `inventario.json`, en la misma carpeta del programa.
- Antes de cada escritura importante se guarda una copia
  `inventario_respaldo_AAAA-MM-DD_HHMMSS.json` (se conservan las 5 ultimas).
- El Excel **nunca** se modifica. La importacion solo lee.
- Reimportar el Excel **no borra** ventas, clientes, precios ni fechas que ya
  tengas en la app: solo actualiza los datos de catalogo del archivo.

## Importar tu Excel

`Archivo > Importar desde Excel...` y elige el `.xlsx`.

El archivo puede tener titulos arriba de la fila 1: la app busca la fila que
empieza con `S/N` y `Marca`. Acepta los 10 campos originales:

`S/N, Marca, Modelo, Tipo, Capacidad, Preciodecompra, Estado, Cliente, PrecioVenta, VenceGarantía`

- La columna `VenceGarantía` puede venir como serial de Excel (`46138.0`);
  la app la convierte a fecha real.
- `FechaVenta` y `FechaEntrada` no hace falta que esten: son nuevas.

## Nube (Firebase)

La app es **local primero**: abre y funciona siempre sin internet y sin
cuenta. La nube solo suma la sincronizacion entre equipos.

Menu `Nube`:

| Opcion | Que hace |
| --- | --- |
| **Iniciar sesion...** | Pide correo y contrasena de tu cuenta de Firebase. |
| **Cerrar sesion** | Olvida la sesion guardada en este equipo (no borra tus datos locales). |
| **Configurar Firebase...** | Cambia la URL de la base. Vacio = solo local. |
| **Probar conexion** | Comprueba la URL y que la sesion tenga permiso. |
| **Sincronizar ahora** | Baja lo remoto y sube lo local. |

### Como queda protegido

- Se usa **Firebase Authentication con correo y contrasena**. No hay token
  compartido ni contrasenas guardadas en el codigo.
- Cada peticion a la base va con `Authorization: Bearer <idToken>`.
- Cuando el token caduca, la app lo renueva sola con el refresh token y
  reintenta la peticion una vez. Si tambien falla, te avisa y cierra la sesion.
- La contrasena **nunca** se guarda: solo se usa en el momento de entrar.
- El refresh token se guarda en `sesion.dat` **cifrado con DPAPI** (solo tu
  cuenta de Windows puede leerlo). Si el equipo no permite cifrar, la app
  **no guarda nada** y te pide la contrasena de nuevo en cada arranque, en vez
  de dejar el token en claro.
- Las reglas de Firebase deben permitir solo a usuarios autenticados:
  ver abajo.

### Reglas de Firebase

Las reglas de la Realtime Database tienen que ser estas:

```json
{
  "rules": {
    "inventario": {
      "productos": {
        ".read": "auth != null",
        ".write": "auth != null",
        ".indexOn": ["S/N", "Marca", "Estado"]
      }
    },
    ".read": false,
    ".write": false
  }
}
```

Sin sesion, Firebase responde `401` y la app no sube ni baja nada.

### Que se guarda en la nube

Un registro por serial en `inventario/productos`. Cada uno lleva un campo
`_mod` con la fecha y hora del ultimo cambio: al sincronizar, cada equipo
conserva la version mas reciente de cada producto, asi que dos equipos pueden
trabajar a la vez sin pisarse.

## Pruebas

```
python pruebas.py
```

No abre la ventana y no toca tus datos: trabaja en una carpeta temporal.
Si encuentra tu `Inventario.xlsx` en la ruta que tiene en el archivo, ademas
prueba la importacion real (364 productos) y que reimportar no borre ventas.

El codigo de autenticacion se prueba aparte, sin red y sin necesitar cuenta:

```
python pruebas_auth.py
```

Ahí se revisa el cifrado de la sesion, que el token nunca quede en claro, que
las peticiones lleven `Authorization`, y que un `401` dispare la renovacion y
un unico reintento.

## Compilar

```
pip install -r requirements.txt
compilar.bat
```

Deja el `.exe` en `dist\InventarioApp.exe`. El instalador solo se genera si hay
Inno Setup 6 instalado; si no, el `.exe` ya se puede usar.

## Estructura

```
inventario.py        toda la app (datos + interfaz)
pruebas.py           pruebas automáticas
config.example.json  plantilla de configuración
instalador.iss       script de Inno Setup
compilar.bat         compila exe + instalador
dist/                salida de PyInstaller
releases/pc/         instaladores
android-app/         app Android (fase siguiente)
```