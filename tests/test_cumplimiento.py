"""Revisor de originales: lo que puede costar la monetización del canal tiene que bloquear."""
import unittest

from fabrica import cumplimiento

FUENTE = (
    "La Gran Inundación de Melaza ocurrió en Boston el 15 de enero de 1919. Un tanque de "
    "almacenamiento de melaza de casi nueve millones de litros se rompió y liberó una ola "
    "que avanzó por las calles del North End a unos cincuenta y cinco kilómetros por hora. "
    "Murieron veintiuna personas y unas ciento cincuenta resultaron heridas."
)

GUION_PROPIO = (
    "Imagina una mañana tibia de invierno en Boston, con el puerto tranquilo y la gente en la calle. "
    "De repente se oye un estruendo metálico, como una ametralladora, y un muro oscuro y pegajoso "
    "baja por el barrio a la velocidad de un auto. No era agua: era melaza, millones de litros. "
    "¿Cómo algo tan dulce terminó siendo tan mortal? La respuesta está en un tanque mal construido, "
    "en pruebas que nadie hizo y en una empresa con prisa por vender alcohol industrial. "
    "Después del juicio cambiaron las reglas: desde entonces, cada estructura así necesita la firma "
    "de un ingeniero. Una tragedia absurda que dejó una lección muy seria sobre la seguridad."
)

META = {"titulo": "La ola de melaza que arrasó un barrio de Boston"}
VISUALES = [{"origen": "pexels"}, {"origen": "pixabay"}, {"origen": "generado"}]


def revisar(guion, **extra):
    return cumplimiento.revisar_original(guion, "", META, False, VISUALES, 60, **extra)


class TestRevisorOriginales(unittest.TestCase):
    def test_guion_de_respaldo_bloquea(self):
        rev = revisar(GUION_PROPIO, motor="respaldo-local", fuentes_texto=FUENTE)
        self.assertIn("Guion escrito para este video", rev["bloqueos"])

    def test_guion_de_modelo_no_bloquea_por_motor(self):
        rev = revisar(GUION_PROPIO, motor="gemini", fuentes_texto=FUENTE)
        self.assertNotIn("Guion escrito para este video", rev["bloqueos"])
        self.assertEqual(rev["bloqueos"], [])

    def test_copiar_las_fuentes_bloquea(self):
        copiado = "Primero, lo básico. " + FUENTE + " ¿Tú sabías esto? Cuéntame abajo."
        rev = revisar(copiado, motor="gemini", fuentes_texto=FUENTE)
        self.assertIn("Sin copiar las fuentes", rev["bloqueos"])

    def test_guion_propio_no_se_marca_como_copia(self):
        rev = revisar(GUION_PROPIO, motor="gemini", fuentes_texto=FUENTE)
        item = next(i for i in rev["items"] if i["nombre"] == "Sin copiar las fuentes")
        self.assertTrue(item["ok"], item["detalle"])

    def test_respaldo_no_supera_el_umbral_de_auto_aprobacion(self):
        # El caso real de la VM: guion de respaldo con frases de la fuente sacaba 100/100
        copiado = "Hay algo de melaza que casi nadie cuenta bien. Primero, lo básico. " + FUENTE
        rev = revisar(copiado, motor="respaldo-local", fuentes_texto=FUENTE)
        self.assertTrue(rev["bloqueos"])
        self.assertLess(rev["puntaje"], 85)

    def test_sin_datos_nuevos_se_comporta_como_antes(self):
        # Llamadas antiguas (sin motor ni fuentes) no ganan ni pierden controles
        rev = revisar(GUION_PROPIO)
        nombres = {i["nombre"] for i in rev["items"]}
        self.assertNotIn("Guion escrito para este video", nombres)
        self.assertNotIn("Sin copiar las fuentes", nombres)


if __name__ == "__main__":
    unittest.main()
