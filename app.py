from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from pathlib import Path
from uuid import uuid4
from PIL import Image
from threading import Timer
import subprocess
import os
import zipfile

app = Flask(__name__)

# Limite total por envio: 5 GB
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024 * 1024

PASTA_UPLOADS = "uploads"
PASTA_CONVERTIDOS = "convertidos"

os.makedirs(PASTA_UPLOADS, exist_ok=True)
os.makedirs(PASTA_CONVERTIDOS, exist_ok=True)

MAX_ARQUIVOS = 5

FORMATOS_AUDIO = ["mp3", "wav", "ogg", "flac", "m4a", "aac"]
FORMATOS_VIDEO = ["mp4", "mov", "webm", "avi", "mkv"]
FORMATOS_IMAGEM = ["png", "jpg", "jpeg", "webp", "bmp", "gif", "tiff", "ico"]

FORMATOS_PERMITIDOS = FORMATOS_AUDIO + FORMATOS_VIDEO + FORMATOS_IMAGEM


def pegar_extensao(nome_arquivo):
    return Path(nome_arquivo).suffix.lower().replace(".", "")


def apagar_arquivo(caminho):
    try:
        if caminho and os.path.exists(caminho):
            tamanho = os.path.getsize(caminho)
            os.remove(caminho)
            print(f"[LIMPEZA] Arquivo apagado: {caminho} | Tamanho: {tamanho} bytes")
        else:
            print(f"[LIMPEZA] Arquivo não encontrado ou já apagado: {caminho}")
    except Exception as erro:
        print(f"[LIMPEZA] Erro ao apagar arquivo {caminho}: {erro}")


def apagar_varios_arquivos(caminhos):
    for caminho in caminhos:
        apagar_arquivo(caminho)


def apagar_arquivos_depois(caminhos, segundos=15):
    def tarefa_limpeza():
        print("[LIMPEZA] Iniciando limpeza programada...")
        apagar_varios_arquivos(caminhos)

    Timer(segundos, tarefa_limpeza).start()


def converter_midia(caminho_entrada, caminho_saida, formato_entrada, formato_saida):
    # Vídeo para MP3
    if formato_entrada in FORMATOS_VIDEO and formato_saida == "mp3":
        comando = [
            "ffmpeg",
            "-y",
            "-i", caminho_entrada,
            "-vn",
            "-acodec", "libmp3lame",
            "-q:a", "2",
            caminho_saida
        ]

    # Vídeo para outro formato de áudio
    elif formato_entrada in FORMATOS_VIDEO and formato_saida in FORMATOS_AUDIO:
        comando = [
            "ffmpeg",
            "-y",
            "-i", caminho_entrada,
            "-vn",
            caminho_saida
        ]

    # Áudio para MP4 com tela preta
    elif formato_entrada in FORMATOS_AUDIO and formato_saida == "mp4":
        comando = [
            "ffmpeg",
            "-y",
            "-i", caminho_entrada,
            "-f", "lavfi",
            "-i", "color=c=black:s=1280x720:r=30",
            "-shortest",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            caminho_saida
        ]

    # Conversão normal de áudio/vídeo
    else:
        comando = [
            "ffmpeg",
            "-y",
            "-i", caminho_entrada,
            caminho_saida
        ]

    resultado = subprocess.run(
        comando,
        capture_output=True,
        text=True
    )

    if resultado.returncode != 0:
        raise Exception("Erro no FFmpeg: " + resultado.stderr)


def converter_imagem(caminho_entrada, caminho_saida, formato_saida):
    imagem = Image.open(caminho_entrada)

    # JPG/JPEG não aceita transparência
    if formato_saida in ["jpg", "jpeg"]:
        tem_transparencia = (
            imagem.mode in ["RGBA", "LA"] or
            (imagem.mode == "P" and "transparency" in imagem.info)
        )

        if tem_transparencia:
            imagem = imagem.convert("RGBA")
            fundo = Image.new("RGB", imagem.size, (255, 255, 255))
            fundo.paste(imagem, mask=imagem.getchannel("A"))
            imagem = fundo
        else:
            imagem = imagem.convert("RGB")

    imagem.save(caminho_saida)


def converter_arquivo(caminho_entrada, caminho_saida, formato_entrada, formato_saida):
    # Imagem para imagem
    if formato_entrada in FORMATOS_IMAGEM and formato_saida in FORMATOS_IMAGEM:
        converter_imagem(
            caminho_entrada,
            caminho_saida,
            formato_saida
        )

    # Áudio/vídeo para áudio/vídeo
    elif formato_entrada in (FORMATOS_AUDIO + FORMATOS_VIDEO) and formato_saida in (FORMATOS_AUDIO + FORMATOS_VIDEO):
        converter_midia(
            caminho_entrada,
            caminho_saida,
            formato_entrada,
            formato_saida
        )

    else:
        raise Exception(f"Conversão não suportada: {formato_entrada} para {formato_saida}")


@app.errorhandler(413)
def arquivo_muito_grande(erro):
    return "Arquivo muito grande. O limite máximo total é 5 GB.", 413


@app.route("/")
def home():
    return render_template(
        "index.html",
        formatos=FORMATOS_PERMITIDOS
    )


@app.route("/converter", methods=["POST"])
def converter():
    arquivos = request.files.getlist("arquivos")
    formatos_saida = request.form.getlist("formatos_saida")

    arquivos = [arquivo for arquivo in arquivos if arquivo.filename != ""]

    if not arquivos:
        return "Nenhum arquivo enviado.", 400

    if len(arquivos) > MAX_ARQUIVOS:
        return f"Você pode converter no máximo {MAX_ARQUIVOS} arquivos por vez.", 400

    if len(formatos_saida) != len(arquivos):
        return "Cada arquivo precisa ter um formato de saída.", 400

    id_lote = uuid4().hex

    arquivos_para_apagar = []
    arquivos_convertidos = []

    try:
        for indice, arquivo in enumerate(arquivos):
            nome_seguro = secure_filename(arquivo.filename)
            formato_entrada = pegar_extensao(nome_seguro)
            formato_saida = formatos_saida[indice].lower().strip()

            if formato_entrada not in FORMATOS_PERMITIDOS:
                raise Exception(f"Formato de entrada não permitido: {formato_entrada}")

            if formato_saida not in FORMATOS_PERMITIDOS:
                raise Exception(f"Formato de saída não permitido: {formato_saida}")

            caminho_entrada = os.path.join(
                PASTA_UPLOADS,
                f"{id_lote}_{indice}_{nome_seguro}"
            )

            nome_base = Path(nome_seguro).stem
            nome_download = f"{nome_base}_convertido.{formato_saida}"
            nome_no_zip = f"{indice + 1}_{nome_download}"

            caminho_saida = os.path.join(
                PASTA_CONVERTIDOS,
                f"{id_lote}_{indice}_{nome_download}"
            )

            arquivo.save(caminho_entrada)

            arquivos_para_apagar.append(caminho_entrada)
            arquivos_para_apagar.append(caminho_saida)

            converter_arquivo(
                caminho_entrada,
                caminho_saida,
                formato_entrada,
                formato_saida
            )

            arquivos_convertidos.append({
                "caminho": caminho_saida,
                "nome_download": nome_download,
                "nome_no_zip": nome_no_zip
            })

        # Se for só 1 arquivo, baixa direto
        if len(arquivos_convertidos) == 1:
            resposta = send_file(
                arquivos_convertidos[0]["caminho"],
                as_attachment=True,
                download_name=arquivos_convertidos[0]["nome_download"]
            )

            apagar_arquivos_depois(arquivos_para_apagar)

            return resposta

        # Se forem vários arquivos, cria ZIP
        caminho_zip = os.path.join(
            PASTA_CONVERTIDOS,
            f"{id_lote}_arquivos_convertidos.zip"
        )

        with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_DEFLATED) as zip_final:
            for item in arquivos_convertidos:
                zip_final.write(
                    item["caminho"],
                    item["nome_no_zip"]
                )

        arquivos_para_apagar.append(caminho_zip)

        resposta = send_file(
            caminho_zip,
            as_attachment=True,
            download_name="arquivos_convertidos.zip"
        )

        apagar_arquivos_depois(arquivos_para_apagar)

        return resposta

    except Exception as erro:
        apagar_varios_arquivos(arquivos_para_apagar)
        return f"Erro ao converter: {erro}", 500


@app.route("/debug-arquivos")
def debug_arquivos():
    uploads = os.listdir(PASTA_UPLOADS)
    convertidos = os.listdir(PASTA_CONVERTIDOS)

    return {
        "uploads": uploads,
        "convertidos": convertidos,
        "total_uploads": len(uploads),
        "total_convertidos": len(convertidos)
    }


if __name__ == "__main__":
    app.run(debug=True)