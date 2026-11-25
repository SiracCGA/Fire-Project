"""
ARMOR-X arayüz sunucusu (Flask)

Kurulum:   pip install flask psutil
Klasör yapısı (Flask standardı):
    proje/
      arayuz.py
      templates/
        index.html
      static/
        style.css
        script.js
        forest.png
        logo.png

Tek başına test:
    python arayuz.py            ->  tarayıcıda http://localhost:5000

Kendi Flask uygulamana eklemek için (flask_worker.py vb.):
    import arayuz
    app.register_blueprint(arayuz.bp)

    arayuz.durum["temp"] = 27.1               # sensör değerini güncelle
    arayuz.durum["esp"] = [True, True, False, False]
    arayuz.durum["radar"] = [60]              # radarda kırmızı yanacak bölge(ler)
    arayuz.log("warning", "Gecikme var")      # log paneline yazar
    arayuz.algilama("Yangın tespit edildi")   # alarm paneline yazar

Not: Kamera route'un (ör. /video_feed) senin mevcut kodunda kalır, burada yok.
"""
import logging
import threading
from collections import deque
import time
import psutil
from flask import Blueprint, Flask, jsonify, render_template, request
from queue import Queue
import uuid

komut_kuyrugu = Queue()
sonuclar = {}


# Arayüze her istekte gönderilen anlık değerler.
# ESP32 / sensör / ai kodun bu sözlüğü güncellesin.
durum = {
    "temp": 0,
    "humidity": 0,
    "gas": False,
    "ir": [0, 0, 0],
    "esp": [False, False, False, False],
    "angle": 0,
    "radar": [],            # kırmızı yanacak bölgeler, örn. [60] ya da [60, 180]
    "fps": [0.0],
    "mode": "auto",         # "manual" | "auto"
    "alarm": False,
}

# Log / algılama olayları (arayüz bunları sırayla bir kere çeker)
_olaylar = deque(maxlen=200)
_son_id = 0
_kilit = threading.Lock()


def _olay_ekle(olay):
    global _son_id
    with _kilit:
        _son_id += 1
        _olaylar.append((_son_id, olay))


def log(seviye, metin):
    """seviye: info | warning | error"""
    _olay_ekle({"log": {"level": seviye, "text": metin}})


def algilama(metin):
    _olay_ekle({"detection": metin})

flag = False
donus = None
degers = None

# ---------- Arayüzden gelen komutlar ----------
def komut_isle(tip, deger):
    if tip == "terminal":
        komut_id = str(uuid.uuid4())

        komut_kuyrugu.put({
            "id": komut_id,
            "value": deger
        })

        return {
            "status": "processing",
            "id": komut_id
        }

    return {}



# ---------- Rotalar ----------
bp = Blueprint("arayuz", __name__)


@bp.route("/")
def ana_sayfa():
    return render_template("index.html")


@bp.route("/api/durum")
def api_durum():
    # ?son=<id>: bu id'den sonraki log/algılama olaylarını da gönder.
    # İlk istekte (son yok) eski olaylar gönderilmez.
    son = request.args.get("son", type=int)
    with _kilit:
        olaylar = [] if son is None else [o for i, o in _olaylar if i > son]
        son_id = _son_id

    mesaj = dict(durum)
    mesaj["cpu"] = psutil.cpu_percent()
    mesaj["ram"] = psutil.virtual_memory().percent
    mesaj["olaylar"] = olaylar
    mesaj["son_id"] = son_id

    cevap = jsonify(mesaj)
    cevap.headers["Cache-Control"] = "no-store"
    return cevap


@bp.route("/api/komut", methods=["POST"])
def api_komut():
    veri = request.get_json(silent=True) or {}
    return jsonify(komut_isle(
        veri.get("cmd"),
        veri.get("value")
    ))
@bp.route("/api/komut/sonuc/<komut_id>", methods=["GET"])
def komut_sonuc(komut_id):

    if komut_id in sonuclar:
        sonuc = sonuclar.pop(komut_id)

        return jsonify({
            "status": "completed",
            "result": sonuc
        })

    return jsonify({
        "status": "processing"
    })

@bp.route("/api/olaylar/temizle", methods=["POST"])
def api_olaylar_temizle():
    with _kilit:
        _olaylar.clear()

    return jsonify({
        "status": "success",
        "message": "Olay kayıtları temizlendi."
    })



# ---------- Tek başına çalıştırma ----------
#if __name__ == "__main__":
#    logging.getLogger("werkzeug").setLevel(logging.WARNING)   # her saniyelik istek terminali doldurmasın
#    app = Flask(__name__)
#    app.register_blueprint(bp)