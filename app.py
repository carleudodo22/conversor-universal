from flask import Flask, render_template, request, send_file
from werkzeug.utils import secure_filename
from pathlib import Path
from uuid import uuid4
from PIL import Image
from threading import Timer
import subprocess
import os
import zipfile
import shutil

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
    except Exception as erro:
        print(f"[LIMPEZA] Erro ao apagar arquivo {caminho}: {erro}")


def apagar_varios_arquivos(caminhos):
    for caminho in caminhos:
        apagar_arquivo(caminho)


def apagar_arquivos_depois(caminhos, segundos=600):
    def tarefa_limpeza():
        print("[LIMPEZA] Iniciando limpeza programada...")
        apagar_varios_arquivos(caminhos)

    Timer(segundos, tarefa_limpeza).start()


def rodar_ffmpeg(argumentos):
    comando = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
    ] + argumentos

    resultado = subprocess.run(
        comando,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True
    )

    if resultado.returncode != 0:
        raise Exception("Erro no FFmpeg: " + resultado.stderr)


def codec_audio_saida(formato_saida):
    if formato_saida == "mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]

    if formato_saida in ["aac", "m4a"]:
        return ["-c:a", "aac", "-b:a", "192k"]

    if formato_saida == "ogg":
        return ["-c:a", "libvorbis", "-q:a", "5"]

    if formato_saida == "flac":
        return ["-c:a", "flac", "-compression_level", "5"]

    if formato_saida == "wav":
        return ["-c:a", "pcm_s16le"]

    return []


def converter_midia(caminho_entrada, caminho_saida, formato_entrada, formato_saida):
    # Saída em áudio
    if formato_saida in FORMATOS_AUDIO:
        argumentos = [
            "-i", caminho_entrada,
            "-vn",
        ]

        argumentos += codec_audio_saida(formato_saida)
        argumentos += [
            "-threads", "0",
            caminho_saida
        ]

        rodar_ffmpeg(argumentos)
        return

    # Áudio para vídeo com tela preta
    if formato_entrada in FORMATOS_AUDIO and formato_saida in FORMATOS_VIDEO:
        if formato_saida == "webm":
            argumentos = [
                "-f", "lavfi",
                "-i", "color=c=black:s=640x360:r=1",
                "-i", caminho_entrada,
                "-shortest",
                "-c:v", "libvpx",
                "-deadline", "realtime",
                "-cpu-used", "8",
                "-b:v", "800k",
                "-c:a", "libvorbis",
                "-q:a", "4",
                caminho_saida
            ]

        elif formato_saida == "avi":
            argumentos = [
                "-f", "lavfi",
                "-i", "color=c=black:s=640x360:r=1",
                "-i", caminho_entrada,
                "-shortest",
                "-c:v", "mpeg4",
                "-q:v", "5",
                "-c:a", "libmp3lame",
                "-q:a", "3",
                caminho_saida
            ]

        else:
            argumentos = [
                "-f", "lavfi",
                "-i", "color=c=black:s=640x360:r=1",
                "-i", caminho_entrada,
                "-shortest",
                "-c:v", "libx264",
                "-preset", "ultrafast",
                "-tune", "stillimage",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                "-threads", "0",
                caminho_saida
            ]

        rodar_ffmpeg(argumentos)
        return

    # Vídeo para vídeo
    if formato_saida in FORMATOS_VIDEO:
        if formato_saida == "webm":
            argumentos = [
                "-i", caminho_entrada,
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c:v", "libvpx",
                "-deadline", "realtime",
                "-cpu-used", "8",
                "-b:v", "1M",
                "-c:a", "libvorbis",
                "-q:a", "4",
                caminho_saida
            ]

        elif formato_saida == "avi":
            argumentos = [
                "-i", caminho_entrada,
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c:v", "mpeg4",
                "-q:v", "5",
                "-c:a", "libmp3lame",
                "-q:a", "3",
                caminho_saida
            ]

        elif formato_saida in ["mp4", "mov"]:
            argumentos = [
                "-i", caminho_entrada,
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                "-threads", "0",
                caminho_saida
            ]

        else:
            argumentos = [
                "-i", caminho_entrada,
                "-map", "0:v:0",
                "-map", "0:a:0?",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "23",
                "-pix_fmt", "yuv420p",
                "-c:a", "aac",
                "-b:a", "192k",
                "-threads", "0",
                caminho_saida
            ]

        rodar_ffmpeg(argumentos)
        return

    raise Exception(f"Conversão de mídia não suportada: {formato_entrada} para {formato_saida}")


def converter_imagem(caminho_entrada, caminho_saida, formato_saida):
    with Image.open(caminho_entrada) as imagem:
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

            imagem.save(caminho_saida, quality=95)

        elif formato_saida == "png":
            imagem.save(caminho_saida, compress_level=1)

        elif formato_saida == "webp":
            if imagem.mode not in ["RGB", "RGBA"]:
                imagem = imagem.convert("RGBA")
            imagem.save(caminho_saida, quality=92, method=0)

        elif formato_saida == "ico":
            imagem.save(caminho_saida, sizes=[(256, 256)])

        else:
            imagem.save(caminho_saida)


def converter_arquivo(caminho_entrada, caminho_saida, formato_entrada, formato_saida):
    # Se for o mesmo formato, não converte. Só copia.
    # Isso deixa arquivos pequenos praticamente instantâneos.
    if formato_entrada == formato_saida:
        shutil.copyfile(caminho_entrada, caminho_saida)
        return

    # Imagem para imagem
    if formato_entrada in FORMATOS_IMAGEM and formato_saida in FORMATOS_IMAGEM:
        converter_imagem(
            caminho_entrada,
            caminho_saida,
            formato_saida
        )
        return

    # Áudio/vídeo para áudio/vídeo
    if formato_entrada in (FORMATOS_AUDIO + FORMATOS_VIDEO) and formato_saida in (FORMATOS_AUDIO + FORMATOS_VIDEO):
        converter_midia(
            caminho_entrada,
            caminho_saida,
            formato_entrada,
            formato_saida
        )
        return

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

        # Se forem vários arquivos, cria ZIP sem compressão.
        # Isso é mais rápido para áudio/vídeo/imagem porque eles já são comprimidos.
        caminho_zip = os.path.join(
            PASTA_CONVERTIDOS,
            f"{id_lote}_arquivos_convertidos.zip"
        )

        with zipfile.ZipFile(caminho_zip, "w", zipfile.ZIP_STORED) as zip_final:
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
