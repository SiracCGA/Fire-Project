import dashboard
import logging
import threading
import time
import queue
from flask import Flask

# LOG AYARLARI
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger("FIRE-TEST")

app = Flask(__name__)
app.register_blueprint(dashboard.bp)

log.info("Dashboard modülü import edildi.")
log.info("Blueprint kaydedildi.")

# Queue kontrolü
log.info("Queue ID: %s", id(dashboard.komut_kuyrugu))


# MAIN KOMUT DÖNGÜSÜ
def komut_dinleyici():

    log.info("Komut dinleyici başlatıldı.")

    while True:
        try:
            komut = dashboard.komut_kuyrugu.get(timeout=1)

            log.info("================================")
            log.info("KOMUT ALINDI: %s", komut)

            komut_id = komut["id"]
            deger = komut["value"]

            log.info("Komut ID: %s", komut_id)
            log.info("Komut değeri: %s", deger)

            try:
                # TEST AMAÇLI
                sonuc = f"Main.py komutu aldı: {deger}"

                log.info("Komut işlendi: %s", sonuc)

                dashboard.sonuclar[komut_id] = sonuc

                log.info("Sonuç dashboard'a gönderildi.")

            except Exception:
                log.exception("Komut işleme hatası!")

        except queue.Empty:
            continue

        except Exception:
            log.exception("Komut dinleyici hatası!")


# TEST ROUTE
@app.route("/test")
def test():

    log.info("TEST ENDPOINT ÇAĞRILDI")

    return {
        "status": "ok",
        "queue_id": id(dashboard.komut_kuyrugu)
    }


if __name__ == "__main__":

    log.info("FIRE PROJECT BAŞLATILIYOR")

    worker = threading.Thread(
        target=komut_dinleyici,
        daemon=True
    )

    worker.start()

    log.info("Komut thread başlatıldı.")

    log.info("Flask başlatılıyor...")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    app.run(
        host="0.0.0.0",
        port=5000,
        threaded=True,
        debug=False,
        use_reloader=False
    )