"""Importación de música de P4: solo entra lo que trae checks reales y aprobados."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fabrica import musica_propia


def tema(isrc, genero="synthwave", certificado=True, checks="sonoridad_lufs=ok;true_peak=ok;sin_clipping=ok"):
    t = {"isrc": isrc, "title": f"Tema {isrc}", "artist": "Shameless Music Engine", "genre": genero,
         "bpm": 120, "duration_sec": 40.0, "audio_filename": f"{isrc}.wav",
         "content_id_certified": certificado, "sample_packs_used": False}
    if checks is not None:
        t["content_id_checks"] = checks
    return t


class TestMusicaPropia(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raiz = Path(self.tmp.name)
        self.origen = raiz / "motor"
        (self.origen / "output" / "metadata").mkdir(parents=True)
        (self.origen / "output" / "audio").mkdir(parents=True)
        self.musica = raiz / "musica"
        parches = [
            mock.patch.object(musica_propia, "MUSICA_DIR", self.musica),
            mock.patch.object(musica_propia, "MANIFIESTO", self.musica / "catalogo_propio.json"),
            # Sin FFmpeg: "convertir" es copiar el WAV al MP3 de destino
            mock.patch("fabrica.media._ff", side_effect=lambda *a: Path(a[-1]).write_bytes(b"mp3")),
        ]
        for p in parches:
            p.start()
            self.addCleanup(p.stop)
        self.addCleanup(self.tmp.cleanup)

    def catalogo(self, temas):
        for t in temas:
            (self.origen / "output" / "audio" / t["audio_filename"]).write_bytes(b"wav")
        (self.origen / "output" / "metadata" / "catalog_content_id.json").write_text(json.dumps(temas), "utf-8")

    def mp3s(self):
        return sorted(p.relative_to(self.musica).as_posix() for p in self.musica.rglob("*.mp3"))

    def test_importa_solo_temas_con_checks_aprobados(self):
        self.catalogo([tema("A"), tema("B", certificado=False, checks="sonoridad_lufs=falla")])
        musica_propia.importar(self.origen)
        self.assertEqual(self.mp3s(), ["curiosidades/A.mp3", "tecnologia/A.mp3"])

    def test_catalogo_viejo_sin_checks_no_entra(self):
        # Antes del 2026-11-01 todo decía certificado=True sin checks detrás
        self.catalogo([tema("A", checks=None)])
        musica_propia.importar(self.origen)
        self.assertEqual(self.mp3s(), [])

    def test_retira_temas_que_dejaron_de_estar_certificados(self):
        self.catalogo([tema("A")])
        musica_propia.importar(self.origen)
        self.catalogo([tema("A", certificado=False, checks="sonoridad_lufs=falla")])
        res = musica_propia.importar(self.origen)
        self.assertEqual(self.mp3s(), [])
        self.assertIn("A.mp3", res.get("retirados", []))
        manifiesto = json.loads((self.musica / "catalogo_propio.json").read_text("utf-8"))
        self.assertNotIn("A.mp3", manifiesto)


if __name__ == "__main__":
    unittest.main()
