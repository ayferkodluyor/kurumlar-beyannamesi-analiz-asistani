import streamlit as st
import fitz
import re
import pandas as pd
from collections import Counter

st.set_page_config(
    page_title="Kurumlar Beyannamesi Analiz Asistanı",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Kurumlar Beyannamesi Analiz Asistanı")

st.write(
    "Kurumlar ve geçici vergi beyannamelerinden kredi değerlendirmesinde "
    "kullanılan temel mali verileri otomatik olarak çıkarır."
)

st.caption(
    "PDF belgelerini yükleyin. Sistem firma, VKN, dönem ve temel mali "
    "verileri analiz ederek belge kontrollerini gerçekleştirir."
)

# --------------------------------------------------
# KABUL EDİLEN DÖNEMLER
# --------------------------------------------------

BEKLENEN_DONEMLER = {
    "2024 Yıl Sonu": {
        "yil": "2024",
        "tip": "Yıl Sonu"
    },
    "2025 Yıl Sonu": {
        "yil": "2025",
        "tip": "Yıl Sonu"
    },
    "2026 2. Dönem": {
        "yil": "2026",
        "tip": "2. Dönem"
    }
}


uploaded_files = st.file_uploader(
    "Beyannameleri yükleyin",
    type=["pdf"],
    accept_multiple_files=True
)


# --------------------------------------------------
# PDF METNİNİ OKU
# --------------------------------------------------

def pdf_metni_oku(file):
    file.seek(0)

    pdf = fitz.open(
        stream=file.read(),
        filetype="pdf"
    )

    metin = ""

    for sayfa in pdf:
        metin += sayfa.get_text() + "\n"

    pdf.close()

    return metin


# --------------------------------------------------
# TUTAR BUL
# --------------------------------------------------

def tutar_bul(metin, alan):

    desen = rf"{alan}\s+([\d\.\,]+)\s*TL"

    sonuc = re.search(
        desen,
        metin,
        re.IGNORECASE
    )

    if sonuc:
        return sonuc.group(1)

    return None


# --------------------------------------------------
# BELGE ANALİZİ
# --------------------------------------------------

def belge_analiz_et(file):

    metin = pdf_metni_oku(file)

    firma = re.search(
        r"Mükellef\s*/\s*Firma\s*:?\s*([^\n]+)",
        metin,
        re.IGNORECASE
    )

    vkn = re.search(
        r"Vergi Kimlik No\s*:?\s*(\d{10})",
        metin,
        re.IGNORECASE
    )

    donem = re.search(
        r"Beyanname Dönemi\s*:?\s*([^\n]+)",
        metin,
        re.IGNORECASE
    )

    net_satislar = tutar_bul(
        metin,
        r"NET SATIŞLAR"
    )

    aktif_toplami = tutar_bul(
        metin,
        r"AKTİF TOPLAMI"
    )

    odenmis_sermaye = tutar_bul(
        metin,
        r"ÖDENMİŞ SERMAYE"
    )

    return {
        "Dosya": file.name,

        "Firma":
            firma.group(1).strip()
            if firma else None,

        "VKN":
            vkn.group(1)
            if vkn else None,

        "Dönem":
            donem.group(1).strip()
            if donem else None,

        "Net Satışlar":
            net_satislar,

        "Aktif Toplamı":
            aktif_toplami,

        "Ödenmiş Sermaye":
            odenmis_sermaye
    }


# --------------------------------------------------
# DOSYALAR YÜKLENDİĞİNDE
# --------------------------------------------------

if uploaded_files:

    tum_belgeler = []
    okunamayanlar = []

    for file in uploaded_files:

        try:
            sonuc = belge_analiz_et(file)

            # Temel bilgiler okunamadıysa geçersiz say
            if (
                sonuc["Firma"] is None
                or sonuc["VKN"] is None
                or sonuc["Dönem"] is None
            ):
                okunamayanlar.append(file.name)

            else:
                tum_belgeler.append(sonuc)

        except Exception:
            okunamayanlar.append(file.name)


    # --------------------------------------------------
    # OKUNAMAYAN BELGELER
    # --------------------------------------------------

    if okunamayanlar:

        for dosya in okunamayanlar:
            st.warning(
                f"⚠️ Belge okunamadı veya gerekli bilgiler bulunamadı: {dosya}"
            )


    if tum_belgeler:

        tum_df = pd.DataFrame(tum_belgeler)


        # --------------------------------------------------
        # ANA FİRMA / VKN TESPİTİ
        # --------------------------------------------------

        vkn_listesi = tum_df["VKN"].dropna().tolist()

        ana_vkn = Counter(vkn_listesi).most_common(1)[0][0]

        ana_firma_satirlari = tum_df[
            tum_df["VKN"] == ana_vkn
        ]

        ana_firma = (
            ana_firma_satirlari["Firma"]
            .dropna()
            .iloc[0]
        )


        st.subheader("🏢 Firma Bilgileri")

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "Firma",
                ana_firma
            )

        with col2:
            st.metric(
                "VKN",
                ana_vkn
            )


        # --------------------------------------------------
        # FARKLI VKN KONTROLÜ
        # --------------------------------------------------

        farkli_vkn_belgeleri = tum_df[
            tum_df["VKN"] != ana_vkn
        ]

        if not farkli_vkn_belgeleri.empty:

            st.error(
                "🚨 Farklı firmaya ait belge tespit edildi."
            )

            for _, satir in farkli_vkn_belgeleri.iterrows():

                st.warning(
                    f"❌ {satir['Dosya']} — "
                    f"{satir['Firma']} / VKN: {satir['VKN']} "
                    "hesaplamaya dahil edilmedi."
                )


        # Sadece ana firmaya ait belgeler
        firma_df = tum_df[
            tum_df["VKN"] == ana_vkn
        ].copy()


        # --------------------------------------------------
        # YANLIŞ DÖNEM KONTROLÜ
        # --------------------------------------------------

        gecerli_satirlar = []
        yanlis_donemler = []

        for index, satir in firma_df.iterrows():

            donem = satir["Dönem"]

            if donem in BEKLENEN_DONEMLER:

                gecerli_satirlar.append(index)

            else:

                yanlis_donemler.append(
                    {
                        "Dosya": satir["Dosya"],
                        "Dönem": donem
                    }
                )


        if yanlis_donemler:

            st.error(
                "🚨 Beklenen dönem dışında belge tespit edildi."
            )

            for belge in yanlis_donemler:

                donem = str(belge["Dönem"])

                if "2024" in donem:

                    beklenen = "2024 Yıl Sonu"

                elif "2025" in donem:

                    beklenen = "2025 Yıl Sonu"

                elif "2026" in donem:

                    beklenen = "2026 2. Dönem"

                else:

                    beklenen = (
                        "2024 Yıl Sonu, "
                        "2025 Yıl Sonu veya "
                        "2026 2. Dönem"
                    )

                st.warning(
                    f"❌ {belge['Dosya']} — "
                    f"Yüklenen dönem: {donem}. "
                    f"Beklenen dönem: {beklenen}. "
                    "Belge analize dahil edilmedi."
                )


        # Yalnızca geçerli dönemler
        gecerli_df = firma_df.loc[
            gecerli_satirlar
        ].copy()


        # --------------------------------------------------
        # MÜKERRER DÖNEM KONTROLÜ
        # --------------------------------------------------

        mukerrer_donemler = []

        if not gecerli_df.empty:

            tekrarlar = gecerli_df[
                gecerli_df.duplicated(
                    subset=["Dönem"],
                    keep=False
                )
            ]

            if not tekrarlar.empty:

                mukerrer_donemler = (
                    tekrarlar["Dönem"]
                    .dropna()
                    .unique()
                    .tolist()
                )

                for donem in mukerrer_donemler:

                    st.error(
                        f"🚨 Mükerrer dönem tespit edildi: {donem}"
                    )

                # Mükerrer dönemleri sonuç tablosundan çıkar
                gecerli_df = gecerli_df[
                    ~gecerli_df["Dönem"].isin(
                        mukerrer_donemler
                    )
                ]


        # --------------------------------------------------
        # EKSİK DÖNEM KONTROLÜ
        # --------------------------------------------------

        mevcut_donemler = set(
            gecerli_df["Dönem"].dropna().tolist()
        )

        beklenen_donemler = set(
            BEKLENEN_DONEMLER.keys()
        )

        eksik_donemler = (
            beklenen_donemler
            - mevcut_donemler
        )


        # --------------------------------------------------
        # SONUÇ TABLOSU
        # --------------------------------------------------

        st.subheader("📑 Mali Veri Analizi")

        if not gecerli_df.empty:

            donem_sirasi = {
                "2024 Yıl Sonu": 1,
                "2025 Yıl Sonu": 2,
                "2026 2. Dönem": 3
            }

            gecerli_df["Sıra"] = (
                gecerli_df["Dönem"]
                .map(donem_sirasi)
            )

            gecerli_df = (
                gecerli_df
                .sort_values("Sıra")
            )

            gosterilecek = gecerli_df[
                [
                    "Dönem",
                    "Net Satışlar",
                    "Aktif Toplamı",
                    "Ödenmiş Sermaye"
                ]
            ].copy()

            gosterilecek = (
                gosterilecek.fillna("—")
            )

            st.dataframe(
                gosterilecek,
                use_container_width=True,
                hide_index=True
            )

        else:

            st.warning(
                "Sonuç tablosuna dahil edilebilecek "
                "geçerli belge bulunamadı."
            )


        # --------------------------------------------------
        # 2026 AKTİF TOPLAMI AÇIKLAMASI
        # --------------------------------------------------

        if (
            "2026 2. Dönem"
            in mevcut_donemler
        ):

            st.info(
                "ℹ️ 2026 yılı Aktif Toplamı kurum içi "
                "sistemde hesaplanan veri olduğundan "
                "bu uygulama kapsamında beyannameden "
                "alınmamaktadır."
            )


        # --------------------------------------------------
        # EKSİK BELGELER
        # --------------------------------------------------

        if eksik_donemler:

            st.warning(
                "⚠️ Analiz için gerekli dönemlerin "
                "tamamı bulunamadı."
            )

            sirali_eksikler = sorted(
                eksik_donemler,
                key=lambda x: {
                    "2024 Yıl Sonu": 1,
                    "2025 Yıl Sonu": 2,
                    "2026 2. Dönem": 3
                }.get(x, 99)
            )

            for donem in sirali_eksikler:

                st.write(
                    f"• Eksik belge: **{donem}**"
                )


        # --------------------------------------------------
        # TAMAMLANMA DURUMU
        # --------------------------------------------------

        if (
            not eksik_donemler
            and not mukerrer_donemler
        ):

            st.success(
                "✅ Gerekli 3 dönem de mevcut. "
                "Mali veri analizi tamamlandı."
            )

        else:

            st.info(
                "ℹ️ Eksik veya hatalı belgeler "
                "tamamlandıktan sonra analiz "
                "tam olarak sonuçlandırılabilir."
            )

else:

    st.info(
        "Analize başlamak için 2024 Yıl Sonu, "
        "2025 Yıl Sonu ve 2026 2. Dönem "
        "beyannamelerini yükleyin."
    )