/* =====================================================
   ARMOR-X ARAYÜZ SCRIPTİ (Flask ile haberleşir)
   Bölümler:
   0. Ayarlar
   1. Yardımcılar
   2. Üst bar (saat, tarih, çalışma süresi)
   3. Arayüz güncelleyiciler (sensör, ESP32, CPU/RAM, log, radar...)
   4. Kamera yayını (Flask HTTP stream)
   5. Flask bağlantısı (durum çekme + komut gönderme)
   6. Çalışma modu ve menü
   7. Terminal
   ===================================================== */

document.addEventListener('DOMContentLoaded', () => {

    /* ===== 0. AYARLAR ===== */
    const CONFIG = {
        // Arayüz Flask'tan açıldığı için adresler göreli (aynı sunucu)
        STREAM_URL: '/video',          // kendi MJPEG route'una göre değiştir
        STREAM_RETRY_MS: 3000,

        POLL_MS: 1000,                      // Python'dan veri çekme aralığı
        POLL_TIMEOUT_MS: 3000,

        MAX_LOG: 100,
        MAX_ALARM: 100,
    };

    /* ===== 1. YARDIMCILAR ===== */
    const $ = (id) => document.getElementById(id);
    const pad = (n) => String(n).padStart(2, '0');
    const saat = () => new Date().toLocaleTimeString('tr-TR');

    // Son gelen değerler (terminal "status" komutu için)
    const durum = { cpu: 0, ram: 0 };

    const el = {
        date: $('dateText'),
        time: $('timeText'),
        uptime: $('uptimeText'),
        statusBar: document.querySelector('.status-bar'),
        statusActive: document.querySelector('.status-active'),

        temp: $('tempValue'),
        humidity: $('humidityValue'),
        gasCard: $('gasCard'),
        gasText: $('gasText'),
        ir: [$('ir1'), $('ir2'), $('ir3')],

        espStatus: document.querySelectorAll('.connection-panel .status-text'),
        cpuBar: document.querySelector('.circle-bar.cpu-color'),
        ramBar: document.querySelector('.circle-bar.ram-color'),

        logScroll: document.querySelector('.log-scroll'),
        alarmBody: $('alarmLogBody'),
        alarmLed: $('alarmStatusLed'),

        radar: document.querySelector('.radar-ekran'),

        pumpGauge: $('pumpGauge'),
        gaugeText: $('gaugeText'),

        terminalInput: $('terminalInput'),
        terminalBody: $('terminalBody'),
    };

    // Elemanlara güvenli yazma (HTML'de yoksa hata vermesin)
    const yaz = (e, text) => { if (e) e.textContent = text; };

    /* ===== 2. ÜST BAR ===== */
    let baslangic = Date.now();

    function ustBarGuncelle() {
        const now = new Date();
        yaz(el.date, now.toLocaleDateString('tr-TR', { day: '2-digit', month: '2-digit', year: 'numeric' }));
        yaz(el.time, now.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }));

        const sn = Math.floor((Date.now() - baslangic) / 1000);
        yaz(el.uptime, `${pad(Math.floor(sn / 3600))}:${pad(Math.floor(sn % 3600 / 60))}:${pad(sn % 60)}`);
    }
    ustBarGuncelle();
    setInterval(ustBarGuncelle, 1000);

    function baglantiDurumuGoster(bagli) {
        if (el.statusBar) el.statusBar.classList.toggle('offline', !bagli);
        yaz(el.statusActive, bagli ? 'Sistem Aktif' : 'Bağlantı Yok');
    }

    /* ===== 3. ARAYÜZ GÜNCELLEYİCİLER ===== */
    function sicaklikGuncelle(v) { yaz(el.temp, Number(v).toFixed(1)); }
    function nemGuncelle(v)      { yaz(el.humidity, Math.round(v)); }

    function gazGuncelle(var_mi) {
        if (!el.gasCard) return;
        el.gasCard.classList.toggle('gas-danger', !!var_mi);
        yaz(el.gasText, var_mi ? 'VAR' : 'YOK');
    }

    // IR: [true, false, true] ya da [1, 0, 1]
    function irGuncelle(dizi) {
        el.ir.forEach((led, i) => {
            if (led && dizi[i] !== undefined) led.classList.toggle('active', !!dizi[i]);
        });
    }

    // ESP32: [true, false, false, false] (sırayla ESP32-1 ... ESP32-4)
    function espGuncelle(dizi) {
        el.espStatus.forEach((e, i) => {
            if (dizi[i] === undefined) return;
            e.textContent = dizi[i] ? 'BAĞLI' : 'BAĞLI DEĞİL';
            e.classList.toggle('online', !!dizi[i]);
        });
    }

    function halkaGuncelle(bar, v) {
        if (!bar) return 0;
        const yuzde = Math.max(0, Math.min(100, Math.round(v)));
        bar.style.setProperty('--value', `${yuzde}%`);
        const ic = bar.querySelector('.circle-inner');
        if (ic) ic.textContent = `${yuzde}%`;
        return yuzde;
    }
    function cpuGuncelle(v) { durum.cpu = halkaGuncelle(el.cpuBar, v); }
    function ramGuncelle(v) { durum.ram = halkaGuncelle(el.ramBar, v); }

    // Kamera yönü (0-360 derece)
    function aciGuncelle(aci) {
        const a = Math.max(0, Math.min(360, Number(aci)));
        if (el.pumpGauge) el.pumpGauge.style.setProperty('--angle', `${a}deg`);
        yaz(el.gaugeText, `${Math.round(a)}°`);
    }

    // Radar: 6 bölge (0°, 60°, 120°, 180°, 240°, 300°). 0° yukarıda, saat yönünde artar.
    const RADAR_ACILAR = [0, 60, 120, 180, 240, 300];
    const radarBolgeleri = {};

    if (el.radar) {
        RADAR_ACILAR.forEach((aci) => {
            const b = document.createElement('div');
            b.className = 'radar-bolge';
            b.style.setProperty('--a', aci);
            el.radar.prepend(b);          // çizgi ve halkaların altında kalsın
            radarBolgeleri[aci] = b;
        });
    }

    // aciler: [60] ya da [60, 180] ya da [] (hepsini söndürür). Tek sayı da olur: 60
    function radarGuncelle(aciler) {
        const liste = Array.isArray(aciler) ? aciler : [aciler];
        RADAR_ACILAR.forEach((aci) => {
            radarBolgeleri[aci].classList.toggle('aktif', liste.includes(aci));
        });
    }

    function fpsGuncelle(kamera, v) {
        yaz($(`fpsValue${kamera}`), Number(v).toFixed(1).replace('.', ','));
    }

    function listeyeEkle(kutu, satir, limit) {
        if (!kutu) return;
        kutu.appendChild(satir);
        while (kutu.children.length > limit) kutu.removeChild(kutu.firstChild);
        kutu.scrollTop = kutu.scrollHeight;
    }

    // seviye: 'info' | 'warning' | 'error'
    function logEkle(seviye, metin) {
        const satir = document.createElement('div');
        satir.className = `log-item ${['info', 'warning', 'error'].includes(seviye) ? seviye : 'info'}`;
        satir.textContent = `[${saat()}] ${metin}`;
        listeyeEkle(el.logScroll, satir, CONFIG.MAX_LOG);
    }

    function algilamaEkle(metin) {
        const satir = document.createElement('div');
        satir.className = 'alarm-line';
        satir.textContent = `> ${metin}`;
        listeyeEkle(el.alarmBody, satir, CONFIG.MAX_ALARM);
    }

    function alarmGuncelle(aktif) {
        if (el.alarmLed) el.alarmLed.classList.toggle('active', !!aktif);
    }

    function modGoster(mod) {
        document.querySelectorAll('.mod-btn').forEach((b) => {
            const bu = b.textContent.trim().toLowerCase() === 'manuel' ? 'manual' : 'auto';
            b.classList.toggle('active', bu === mod);
        });
    }

    /* ===== 4. KAMERA YAYINI (Flask HTTP stream) ===== */
    function yayinBaslat(no, url) {
        const img = $(`pythonStream${no}`);
        if (!img || !url) return;

        const baglan = () => {
            img.style.display = '';
            img.src = `${url}?t=${Date.now()}`;   // önbelleği atla
        };

        img.onerror = () => {
            img.style.display = 'none';
            setTimeout(baglan, CONFIG.STREAM_RETRY_MS);
        };

        baglan();
    }
    yayinBaslat(1, CONFIG.STREAM_URL);

    /* ===== 5. FLASK BAĞLANTISI ===== */
    let bagli = false;
    let sonId = null;       // en son alınan log/algılama olay numarası

    // Python'dan gelen mesaj, birden fazla alan içerebilir.
    function mesajIsle(m) {
        if (m.temp !== undefined)     sicaklikGuncelle(m.temp);
        if (m.humidity !== undefined) nemGuncelle(m.humidity);
        if (m.gas !== undefined)      gazGuncelle(m.gas);
        if (m.ir !== undefined)       irGuncelle(m.ir);
        if (m.esp !== undefined)      espGuncelle(m.esp);
        if (m.cpu !== undefined)      cpuGuncelle(m.cpu);
        if (m.ram !== undefined)      ramGuncelle(m.ram);
        if (m.angle !== undefined)    aciGuncelle(m.angle);
        if (m.radar !== undefined)    radarGuncelle(m.radar);
        if (m.mode !== undefined)     modGoster(m.mode);
        if (m.alarm !== undefined)    alarmGuncelle(m.alarm);
        if (m.uptime !== undefined)   baslangic = Date.now() - m.uptime * 1000;

        // FPS: [28.7] (kamera 1), [28.7, 0] (kamera 1 ve 2)
        if (Array.isArray(m.fps)) m.fps.forEach((v, i) => fpsGuncelle(i + 1, v));

        if (m.log)       logEkle(m.log.level, m.log.text);
        if (m.detection) algilamaEkle(m.detection);
        if (m.terminal !== undefined) terminalSatiriEkle(m.terminal, true);
    }

    function baglantiKoptu() {
        if (!bagli) return;                 // zaten kopuk, tekrar yazma
        bagli = false;
        baglantiDurumuGoster(false);
        espGuncelle([false, false, false, false]);
        logEkle('error', 'BAĞLANTI KESİLDİ! Yeniden deneniyor...');
    }

    // Durumu çek, bitince POLL_MS sonra tekrar çek (istekler üst üste binmez)
    async function durumCek() {
        try {
            const url = sonId === null ? '/api/durum' : `/api/durum?son=${sonId}`;
            const r = await fetch(url, { cache: 'no-store', signal: AbortSignal.timeout(CONFIG.POLL_TIMEOUT_MS) });
            if (!r.ok) throw new Error(`HTTP ${r.status}`);
            const m = await r.json();

            if (!bagli) {
                bagli = true;
                baglantiDurumuGoster(true);
                logEkle('info', 'Sunucuya bağlanıldı.');
            }

            const olaylar = m.olaylar || [];
            if (m.son_id !== undefined) sonId = m.son_id;
            delete m.olaylar;
            delete m.son_id;

            olaylar.forEach(mesajIsle);     // log / algılama satırları
            mesajIsle(m);                   // anlık değerler
        } catch (hata) {
            baglantiKoptu();
        } finally {
            setTimeout(durumCek, CONFIG.POLL_MS);
        }
    }

    baglantiDurumuGoster(false);
    durumCek();

    // Python'a komut yolla: komutGonder('mode', 'manual'). Başarılıysa true döner.
    async function komutGonder(cmd, value) {
        try {
            const r = await fetch('/api/komut', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ cmd, value }),
                signal: AbortSignal.timeout(CONFIG.POLL_TIMEOUT_MS),
            });

            if (!r.ok) throw new Error(`HTTP ${r.status}`);

            const data = await r.json();

            // Normal komut (mode vb.)
            if (data.mode !== undefined) {
                mesajIsle(data);
                return true;
            }

            // Terminal komutu
            if (data.status === "processing" && data.id) {
                komutSonucBekle(data.id);
                return true;
            }

            return false;

        } catch (hata) {
            console.error("Komut hatası:", hata);
            return false;
        }
    }

    async function komutSonucBekle(id) {
        try {
            const r = await fetch(`/api/komut/sonuc/${id}`, {
                signal: AbortSignal.timeout(CONFIG.POLL_TIMEOUT_MS)
            });

            if (!r.ok) throw new Error(`HTTP ${r.status}`);

            const data = await r.json();

            if (data.status === "completed") {
                mesajIsle({
                    terminal: data.result
                });
                return;
            }

            if (data.status === "processing") {
                setTimeout(() => komutSonucBekle(id), 300);
            }

        } catch (hata) {
            console.error("Sonuç bekleme hatası:", hata);
            setTimeout(() => komutSonucBekle(id), 1000);
        }
    }


    /* ===== 6. ÇALIŞMA MODU VE MENÜ ===== */
    // HTML'deki onclick="modSec(this)" bunu çağırır
    window.modSec = async function (btn) {
        const mod = btn.textContent.trim().toLowerCase() === 'manuel' ? 'manual' : 'auto';
        modGoster(mod);
        if (!(await komutGonder('mode', mod))) {
            logEkle('warning', 'Mod değişikliği gönderilemedi: sunucu bağlı değil.');
        }
    };

    // HTML'deki onclick="menuSec(this)" bunu çağırır
    window.menuSec = function (e) {
        document.querySelectorAll('.nav-item').forEach((i) => i.classList.remove('active'));
        e.classList.add('active');
        // Buraya sayfa/panel değiştirme kodu eklenebilir
    };

    /* ===== 7. TERMİNAL ===== */
    function terminalSatiriEkle(metin, cevap = false) {
        if (!el.terminalBody) return;
        const satir = document.createElement('div');
        satir.className = cevap ? 'terminal-line reply' : 'terminal-line';
        satir.textContent = metin;
        el.terminalBody.appendChild(satir);
        el.terminalBody.scrollTop = el.terminalBody.scrollHeight;
    }

    if (el.terminalInput && el.terminalBody) {
        el.terminalInput.addEventListener('keydown', async function (e) {
            if (e.key !== 'Enter') return;

            const komut = this.value.trim();
            if (komut === '') return;
            this.value = '';

            terminalSatiriEkle(`sh~: ${komut}`);
            const kucuk = komut.toLowerCase();

            // Tarayıcıda çözülen komutlar
            if (kucuk === 'clear') {
                // Terminali temizle
                el.terminalBody.innerHTML = '';

                // Arayüzdeki log ve algılama kayıtlarını temizle
                if (el.logScroll) el.logScroll.innerHTML = '';
                if (el.alarmBody) el.alarmBody.innerHTML = '';

                // Python tarafındaki olay kayıtlarını da temizle
                try {
                    const r = await fetch('/api/olaylar/temizle', {
                        method: 'POST',
                        signal: AbortSignal.timeout(CONFIG.POLL_TIMEOUT_MS)
                    });

                    if (!r.ok) throw new Error(`HTTP ${r.status}`);

                } catch (hata) {
                    console.error('Olaylar temizlenemedi:', hata);
                    terminalSatiriEkle('Python tarafındaki olaylar temizlenemedi!', true);
                }
            } else if (kucuk === 'help') {
                terminalSatiriEkle("Mevcut komutlar: help, clear, status, connect (diğerleri Python'a gönderilir)", true);
            } else if (kucuk === 'status') {
                terminalSatiriEkle(`Sunucu: ${bagli ? 'bağlı' : 'bağlı değil'}. CPU: %${durum.cpu}, RAM: %${durum.ram}`, true);
            } else if (kucuk === 'connect') {
                terminalSatiriEkle(bagli ? 'Sunucuya zaten bağlı.' : 'Sunucu yanıt vermiyor, otomatik yeniden deneniyor...', true);
            } else {
                // Diğer her şeyi Python'a yolla, cevap {"terminal": "..."} olarak döner
                if (!(await komutGonder('terminal', komut))) {
                    terminalSatiriEkle(`'${komut}' gönderilemedi: sunucu bağlı değil.`, true);
                }
            }
        });

        const panel = document.querySelector('.terminal-panel');
        if (panel) panel.addEventListener('click', () => el.terminalInput.focus());
    }
});