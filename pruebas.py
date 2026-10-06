"""Pruebas de InventarioApp. Se ejecutan sin abrir la ventana principal.

    python pruebas.py

Si el Excel de ejemplo existe en la ruta de abajo, se usa para probar la
importacion real. Si no, esas pruebas se saltan.
"""

import importlib.util
import json
import os
import shutil
import sys
import tempfile
from datetime import date

APP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "inventario.py")
XLSX = r"C:\Users\Hei\Downloads\Inventario\Inventario.xlsx"


def cargar_app():
    spec = importlib.util.spec_from_file_location("inventario_app", APP)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


fallas = []
saltadas = []


def revisar(nombre, condicion, detalle=""):
    if condicion:
        print("  OK    " + nombre)
    else:
        print("  FALLA " + nombre + (" -> " + str(detalle) if detalle else ""))
        fallas.append(nombre)


def revisar_igual(nombre, obtenido, esperado):
    revisar(nombre, obtenido == esperado, "obtenido {0!r}, esperado {1!r}".format(obtenido, esperado))


def saltar(nombre, motivo):
    print("  SALTA " + nombre + " (" + motivo + ")")
    saltadas.append(nombre)


def seccion(titulo):
    print()
    print(titulo)


def main():
    if not os.path.exists(APP):
        print("No se encuentra inventario.py junto a este archivo.")
        return 1
    inv = cargar_app()
    temporal = tempfile.mkdtemp(prefix="inventario_pruebas_")
    inv.ruta_base = lambda: temporal
    if os.path.exists(os.path.join(temporal, "inventario.json")):
        os.remove(os.path.join(temporal, "inventario.json"))

    try:
        # ---------------------------------------------------------------
        seccion("1. Fechas")
        for entrada, esperado in [
                ("2026-10-05", "05/10/2026"), ("05/10/2026", "05/10/2026"),
                ("26/04/2026", "26/04/2026"), ("46138.0", "26/04/2026"),
                (46138.0, "26/04/2026"), ("N/A", ""), ("", ""), (None, ""),
                ("no es fecha", "")]:
            revisar_igual("formatear_fecha({0!r})".format(entrada),
                          inv.formatear_fecha(entrada), esperado)
        revisar_igual("a_iso('46138.0')", inv.a_iso("46138.0"), "2026-04-26")
        revisar_igual("a_iso('N/A')", inv.a_iso("N/A"), "")
        revisar("a_fecha('') es None", inv.a_fecha("") is None)

        seccion("2. Aritmetica de garantia (meses calendario)")
        for f, m, e in [(date(2026, 10, 5), 12, date(2027, 10, 5)),
                        (date(2026, 1, 31), 1, date(2026, 2, 28)),
                        (date(2026, 10, 5), 0, date(2026, 10, 5)),
                        (date(2024, 2, 29), 12, date(2025, 2, 28))]:
            revisar_igual("sumar_meses({0}, {1})".format(f, m), inv.sumar_meses(f, m), e)

        seccion("3. Lectura de precios tolerante")
        for entrada, esperado in [("1.500.000", 1500000), ("1.200,50", 1200),
                                 ("$90000", 90000), ("95.000", 95000), ("abc", 0),
                                 ("", 0), (None, 0), (95000, 95000), ("-500", -500)]:
            revisar_igual("a_entero({0!r})".format(entrada), inv.a_entero(entrada), esperado)

        seccion("4. Seriales pegados (no se deben danar)")
        for texto, esperado in [
                ("sn-nuevo-001\nsn-nuevo-002\nsn-nuevo-001\n", ["SN-NUEVO-001", "SN-NUEVO-002"]),
                ("SN12345", ["SN12345"]),
                ("S/N: ES10626MA253940306", ["ES10626MA253940306"]),
                ("ESN500-SN9", ["ESN500-SN9"]),
                ("ABC123, DEF456; GHI789", ["ABC123", "DEF456", "GHI789"]),
                ("46138.0", ["46138"]),
                ("ABC.012", ["ABC.012"]),
                ("A1\nB22", ["A1", "B22"])]:
            revisar_igual("limpiar_seriales({0!r})".format(texto),
                          inv.limpiar_seriales(texto), esperado)
        revisar_igual("texto vacio", inv.limpiar_seriales(""), [])
        revisar_igual("solo espacios", inv.limpiar_seriales("  \n "), [])

        seccion("5. Claves de Firebase (sin colisiones ni caracteres prohibidos)")
        revisar_igual("serial normal", inv.clave_firebase("ES10626MA253940306"), "ES10626MA253940306")
        revisar("guion bajo se mantiene", inv.clave_firebase("AB_CD") == "AB_CD")
        con_barra = inv.clave_firebase("AB/CD")
        revisar("la barra se sanea", "/" not in con_barra, con_barra)
        revisar("es determinista", inv.clave_firebase("AB/CD") == con_barra)
        revisar("AB/CD y AB_CD no chocan", inv.clave_firebase("AB_CD") != con_barra)
        prohibidos = set(".#$[]/")
        muestras = [inv.clave_firebase(s) for s in ["A.B", "A#B", "A$B", "A[B", "A]B", "A/B"]]
        revisar("sin caracteres prohibidos en Firebase",
                all(not (set(c) & prohibidos) for c in muestras), muestras)

        seccion("6. Normalizacion de registros")
        almacen = inv.Almacen()
        base = {"S/N": "x1", "Marca": "ediloca", "Modelo": "es106", "Tipo": "SSD SATA",
                "Capacidad": "256GB", "Preciodecompra": "115000.5", "Estado": "Disponible",
                "Cliente": "", "PrecioVenta": "120000", "VenceGarantía": "46138.0",
                "FechaVenta": "", "FechaEntrada": ""}
        r = almacen.normalizar(dict(base))
        revisar_igual("Marca en mayusculas", r["Marca"], "EDILOCA")
        revisar_igual("Modelo en mayusculas", r["Modelo"], "ES106")
        revisar_igual("Tipo se respeta tal cual", r["Tipo"], "SSD SATA")
        revisar_igual("Precio a entero", r["Preciodecompra"], 115000)
        revisar_igual("Garantia de Excel a ISO", r["VenceGarantía"], "2026-04-26")
        revisar_igual("Cliente vacio -> N/A", r["Cliente"], "N/A")
        revisar_igual("Estado vacio -> Disponible", r["Estado"], "Disponible")
        r2 = almacen.normalizar(dict(base, Tipo="M.2 NVMe", VenceGarantía="N/A"))
        revisar_igual("'M.2 NVMe' intacto", r2["Tipo"], "M.2 NVMe")
        revisar_igual("'N/A' -> vacio", r2["VenceGarantía"], "")

        seccion("7. Altas, ventas, busqueda y borrado")
        almacen.agregar(dict(base, **{"S/N": "A1", "Estado": "Disponible"}))
        almacen.agregar(dict(base, **{"S/N": "A2", "Estado": "Disponible"}))
        revisar_igual("2 registros", len(almacen.registros), 2)
        revisar_igual("contar()", almacen.contar(), (2, 0))
        almacen.actualizar_serial("A2", {"Estado": "Vendido", "Cliente": "JUAN",
                                         "FechaVenta": "2026-10-05"})
        revisar_igual("venta aplicada", almacen.por_serial("A2")["Estado"], "Vendido")
        revisar_igual("FechaVenta guardada", almacen.por_serial("A2")["FechaVenta"], "2026-10-05")
        revisar_igual("el otro sigue disponible", almacen.por_serial("A1")["Estado"], "Disponible")
        revisar_igual("el otro sin FechaVenta", almacen.por_serial("A1")["FechaVenta"], "")
        revisar_igual("contar() tras venta", almacen.contar(), (1, 1))
        revisar_igual("buscar por marca", len(almacen.buscar("ediloca")), 2)
        revisar_igual("buscar por cliente", len(almacen.buscar("juan")), 1)
        revisar_igual("busqueda vacia", len(almacen.buscar("")), 2)
        revisar_igual("sin resultados", len(almacen.buscar("ZZZ")), 0)

        seccion("8. Guardado y respaldos")
        almacen.guardar()
        ruta = os.path.join(temporal, "inventario.json")
        revisar("archivo creado", os.path.exists(ruta))
        with open(ruta, encoding="utf-8") as f:
            guardado = json.load(f)
        revisar_igual("productos en disco", len(guardado["productos"]), 2)
        recargado = inv.Almacen()
        recargado.cargar()
        revisar_igual("recarga identica", len(recargado.registros), 2)
        revisar_igual("venta sobrevive al reinicio",
                       recargado.por_serial("A2")["FechaVenta"], "2026-10-05")
        for _ in range(inv.LIMITE_RESPALDOS + 3):
            almacen.respaldo_local()
        respaldos = [f for f in os.listdir(temporal) if f.startswith("inventario_respaldo_")]
        revisar("respaldos limitados a {0}".format(inv.LIMITE_RESPALDOS),
                len(respaldos) <= inv.LIMITE_RESPALDOS, "{0} archivos".format(len(respaldos)))
        revisar("no quedan .tmp", not any(f.endswith(".tmp") for f in os.listdir(temporal)))

        seccion("9. Sincronizador (sin tocar la red)")
        revisar("activo con URL", inv.Sincronizador("https://x.firebaseio.com").activo)
        revisar("inactivo sin URL", not inv.Sincronizador("").activo)
        revisar_igual("quita la barra final",
                       inv.Sincronizador("https://x.firebaseio.com///").url, "https://x.firebaseio.com")
        revisar_igual("ruta de productos", inv.Sincronizador.RUTA_BASE, "inventario/productos")
        try:
            inv.Sincronizador("")._pedir("GET", "")
            revisar("sin URL avisa antes de la red", False, "no dio error")
        except RuntimeError as e:
            revisar("sin URL avisa antes de la red", "No hay URL" in str(e))
        import inspect
        fuente = inspect.getsource(inv.Sincronizador.subir)
        revisar("subir() manda _mod para resolver conflictos", '"_mod"' in fuente)

        seccion("10. Configuracion")
        inv.guardar_config("https://prueba.firebaseio.com/")
        revisar_igual("guarda la URL", inv.leer_config()["sync_url"], "https://prueba.firebaseio.com/")
        inv.guardar_config("")
        revisar_igual("config vacia", inv.leer_config()["sync_url"], "")

        # ---------------------------------------------------------------
        if not os.path.exists(XLSX):
            saltar("Importacion del Excel real", "no esta " + XLSX)
        else:
            seccion("11. Importacion del Excel real")
            filas = inv.leer_xlsx(XLSX)
            revisar("lee el archivo", len(filas) > 0, "{0} filas".format(len(filas)))
            revisar_igual("10 columnas originales", filas[0], inv.COLUMNAS[:10])
            destino = inv.Almacen()
            nuevos, actualizados = inv.importar_filas(destino, filas)
            revisar_igual("importa todos los productos", len(destino.registros), 364)
            revisar_igual("todos nuevos", (nuevos, actualizados), (364, 0))
            revisar("ningun serial vacio", all(r["S/N"] for r in destino.registros))
            revisar("ningun serial repetido",
                    len({r["S/N"] for r in destino.registros}) == 364)
            revisar("precios con valor",
                    all(r["Preciodecompra"] > 0 for r in destino.registros))
            revisar("precios como enteros",
                    all(isinstance(r["Preciodecompra"], int) for r in destino.registros))
            revisar("los registros viejos no inventan fechas",
                    all(r["FechaVenta"] == "" for r in destino.registros))
            revisar("conserva 'M.2 NVMe'",
                    "M.2 NVMe" in {r["Tipo"] for r in destino.registros})

            seccion("12. Reimportar NO borra ventas ni fechas")
            vendido = next(r["S/N"] for r in destino.registros if r["Estado"] == "Vendido")
            destino.actualizar_serial(vendido, {"FechaVenta": "2026-10-01",
                                                "FechaEntrada": "2026-06-15",
                                                "Cliente": "CLIENTE PRUEBA",
                                                "PrecioVenta": 999999})
            destino.guardar()
            nuevos2, actualizados2 = inv.importar_filas(destino, filas)
            revisar_igual("no crea duplicados", len(destino.registros), 364)
            revisar_igual("marca todo como actualizacion", (nuevos2, actualizados2), (0, 364))
            despues = destino.por_serial(vendido)
            revisar_igual("conserva FechaVenta", despues["FechaVenta"], "2026-10-01")
            revisar_igual("conserva FechaEntrada", despues["FechaEntrada"], "2026-06-15")
            revisar_igual("conserva el cliente", despues["Cliente"], "CLIENTE PRUEBA")
            revisar_igual("conserva el precio de venta", despues["PrecioVenta"], 999999)
            revisar_igual("sigue vendido", despues["Estado"], "Vendido")

            seccion("13. Encabezados mal formados")
            for filas_malas, descripcion in [([["col A", "col B"], ["a", "b"]], "sin titulos"),
                                             ([["Columna A", "Columna B"]], "sin S/N")]:
                try:
                    inv.encontrar_mapa(filas_malas)
                    revisar("rechaza archivo {0}".format(descripcion), False, "no dio error")
                except ValueError:
                    revisar("rechaza archivo {0}".format(descripcion), True)

    finally:
        shutil.rmtree(temporal, ignore_errors=True)

    print()
    print("=" * 58)
    if fallas:
        print("FALLARON {0} de las pruebas:".format(len(fallas)))
        for f in fallas:
            print("  - " + f)
        return 1
    print("Todas las pruebas pasaron." + (
        " ({0} omitidas)".format(len(saltadas)) if saltadas else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())