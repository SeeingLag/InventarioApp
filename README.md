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

## Nube (Firebase) — pendiente de configurar

La app arranca **siempre en modo local**, sin nube. Para activarla:
`Herramientas > Configurar Firebase` y pega la URL de tu Realtime Database.

> Importante: hoy la app se conecta con la URL sola, sin usuario ni contrasena.
> Eso solo es aceptable si las reglas de Firebase son publicas, lo cual
> **no** es lo que queremos. Antes de subir datos reales hay que definir la
> autenticacion (ver `Sincronizacion` en la lista de pendientes).

## Pruebas

```
python pruebas.py
```

No abre la ventana y no toca tus datos: trabaja en una carpeta temporal.
Si encuentra tu `Inventario.xlsx` en la ruta que tiene en el archivo, ademas
prueba la importacion real (364 productos) y que reimportar no borre ventas.

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