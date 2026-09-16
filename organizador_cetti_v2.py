import os
import shutil
import time
from pathlib import Path

import google.genai as genai
from importlib.metadata import PackageNotFoundError, version as package_version

from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler
from watchdog.observers.polling import PollingObserver

from cetti_core import abrir_local, buscar_documentos, garantir_estrutura, obter_raiz, resumo_caminho
from cetti_interaction import aguardar_resposta, criar_pedido_cliente, limpar_pedido
from cetti_logging import log_monitor


load_dotenv()

try:
    SDK_VERSION = package_version("google-genai")
except PackageNotFoundError:
    SDK_VERSION = "desconhecida"

log_monitor(f"🚀 Iniciando Arquivista Digital Inteligente da Cetti... (Versão SDK: {SDK_VERSION})")


def carregar_api_key():
    chave = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not chave:
        return None

    chave = chave.split("#", 1)[0].strip()
    return chave or None


def eh_erro_autenticacao_ou_servico(erro_texto):
    texto = str(erro_texto)
    return (
        "API key not valid" in texto
        or "API_KEY_INVALID" in texto
        or "403" in texto
        or "401" in texto
        or "503" in texto
        or "ServiceUnavailable" in texto
    )


api_key = carregar_api_key()
if not api_key:
    raise SystemExit("❌ ERRO: defina GEMINI_API_KEY no arquivo .env ou na variável de ambiente.")

try:
    client = genai.Client(api_key=api_key)
    modelo_gemini = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
except Exception as e:
    log_monitor(f"❌ ERRO ao configurar o Gemini: {e}")
    raise SystemExit(1)


EXTENSOES_PERMITIDAS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".jpg", ".jpeg", ".png", ".txt")

PROMPT_SISTEMA = """
Você é um assistente jurídico especializado em triagem.
Analise o conteúdo do arquivo e identifique:
1. Nome completo do Cliente.
2. Tipo exato do documento (ex: Petição Inicial, RG, Comprovante de Residência, Contrato Honorários).

RETORNE APENAS um JSON puro (sem markdown):
- Se conseguir identificar, use o nome exato
- Se NÃO conseguir identificar, use exatamente: "DESCONHECIDO"
- Nunca retorne vazio, nunca retorne "NOME_OU_DESCONHECIDO", sempre preencha com o nome ou "DESCONHECIDO"

Exemplo:
{"cliente": "Maria Santos", "tipo": "Petição Inicial"}
ou
{"cliente": "DESCONHECIDO", "tipo": "OUTROS"}
"""

RAIZ = obter_raiz()
ADVOGADO_PADRAO = os.getenv("ADVOGADO_PADRAO", "DESCONHECIDO").strip() or "DESCONHECIDO"

if RAIZ is None:
    raise SystemExit("ERRO: a pasta Documentos do Windows nao foi localizada")

pastas = garantir_estrutura(RAIZ)
ENTRADA = pastas["entrada"]
NAO_PROTOCOLADO = pastas["nao_protocolado"]
PROTOCOLADO = pastas["protocolado"]


class Handler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory and event.src_path.lower().endswith(EXTENSOES_PERMITIDAS):
            arquivo = os.path.basename(event.src_path)
            log_monitor(f"✨ Novo arquivo detectado: {arquivo}")
            time.sleep(2)
            processar_arquivo(Path(event.src_path))


def extrair_json_puro(texto: str) -> dict:
    json_str = texto.replace("```json", "").replace("```", "").strip()
    return __import__("json").loads(json_str)


def identificar_com_ia(caminho_arquivo: Path) -> tuple[str, str]:
    nome_arquivo = caminho_arquivo.name
    log_monitor(f"📤 Fazendo upload para análise: {nome_arquivo}")

    try:
        doc_ia = client.files.upload(file=str(caminho_arquivo))
    except Exception as e:
        if eh_erro_autenticacao_ou_servico(e):
            raise RuntimeError(
                "ERRO ao fazer upload no Gemini: a chave foi rejeitada ou o serviço respondeu com falha."
            ) from e
        raise RuntimeError(f"ERRO no upload para o Gemini: {e}") from e

    while getattr(doc_ia, "state", None) and doc_ia.state.name == "PROCESSING":
        log_monitor("⏳ IA processando arquivo...")
        time.sleep(2)
        doc_ia = client.files.get(name=doc_ia.name)

    if getattr(doc_ia, "state", None) and doc_ia.state.name == "FAILED":
        raise RuntimeError("IA falhou ao ler este arquivo.")

    try:
        response = client.models.generate_content(
            model=modelo_gemini,
            contents=[PROMPT_SISTEMA, doc_ia],
        )
    except Exception as e:
        if eh_erro_autenticacao_ou_servico(e):
            raise RuntimeError(
                "ERRO ao solicitar análise ao Gemini: autenticação rejeitada ou serviço indisponível."
            ) from e
        raise RuntimeError(f"ERRO ao solicitar análise ao Gemini: {e}") from e

    data = extrair_json_puro(response.text)
    cliente = str(data.get("cliente", "DESCONHECIDO")).strip() or "DESCONHECIDO"
    tipo = str(data.get("tipo", "OUTROS")).strip() or "OUTROS"
    return cliente, tipo


def processar_arquivo(caminho_arquivo):
    nome_arquivo = caminho_arquivo.name
    try:
        cliente, tipo = identificar_com_ia(caminho_arquivo)
    except Exception as e:
        log_monitor(f"❌ Erro crítico na IA para {nome_arquivo}: {e}")
        return

    esta_assinado = "assinado" in nome_arquivo.lower()

    if cliente == "DESCONHECIDO":
        log_monitor(f"⚠️ IA com dúvida para {nome_arquivo}.")

    if cliente == "DESCONHECIDO":
        pedido_id = criar_pedido_cliente(nome_arquivo, ADVOGADO_PADRAO, tipo)
        log_monitor(f"❓ Cliente não reconhecido para {nome_arquivo}. Aguardando resposta no chat...")
        try:
            cliente = aguardar_resposta(pedido_id, timeout=int(os.getenv("CLIENTE_PROMPT_TIMEOUT", "900")))
            cliente = cliente.strip() or "DESCONHECIDO"
            log_monitor(f"💬 Cliente informado no chat para {nome_arquivo}: {cliente}")
        except TimeoutError:
            log_monitor(f"⏰ Tempo esgotado aguardando cliente para {nome_arquivo}. Usando DESCONHECIDO.")
            cliente = "DESCONHECIDO"
        finally:
            limpar_pedido(pedido_id)

    log_monitor(f"✅ IA identificou {cliente} (Adv: {ADVOGADO_PADRAO})")

    cliente = cliente.strip().upper()
    tipo = tipo.strip().title()

    pasta_destino_nao = NAO_PROTOCOLADO / cliente / tipo
    pasta_destino_sim = PROTOCOLADO / cliente / tipo
    pasta_destino_nao.mkdir(parents=True, exist_ok=True)

    if esta_assinado:
        pasta_destino_sim.mkdir(parents=True, exist_ok=True)
        shutil.move(str(caminho_arquivo), str(pasta_destino_sim / nome_arquivo))
        log_monitor(f"✅ Documento assinado movido para Protocolados: {nome_arquivo}")
    else:
        shutil.move(str(caminho_arquivo), str(pasta_destino_nao / nome_arquivo))
        log_monitor(f"📂 Documento original movido para Não Protocolados: {nome_arquivo}")


def chatbot():
    print("\n🤖 Cetti Agentics V2 - Atendimento Jurídico Online")
    print("Comandos: 'buscar [termo]', 'sair'")

    while True:
        pergunta = input("\nVocê > ").strip()
        pergunta_normalizada = pergunta.lower()

        if "sair" in pergunta_normalizada:
            break

        if "buscar" in pergunta_normalizada or "onde" in pergunta_normalizada:
            termo = pergunta_normalizada.replace("buscar", "").replace("onde está", "").replace("onde", "").strip()
            if not termo:
                print("❌ Informe um nome de cliente, documento ou trecho do caminho.")
                continue

            resultados = buscar_documentos(termo, RAIZ)

            if resultados:
                print(f"🔍 Encontrei {len(resultados)} arquivo(s):")
                for i, r in enumerate(resultados):
                    print(f"{i+1}. {resumo_caminho(r, RAIZ)}")

                escolha = input("Digite o número para abrir a pasta (ou 'n'): ")
                if escolha.isdigit():
                    indice = int(escolha) - 1
                    if 0 <= indice < len(resultados):
                        abrir_local(resultados[indice].parent)
            else:
                print("❌ Não encontrei documentos com esse nome.")


if __name__ == "__main__":
    def varrer_arquivos_existentes():
        """Processa arquivos já existentes na pasta de entrada."""
        if not ENTRADA.exists():
            return
        
        arquivos = [arquivo for arquivo in ENTRADA.iterdir() if arquivo.is_file() and arquivo.suffix.lower() in EXTENSOES_PERMITIDAS]
        if arquivos:
            log_monitor(f"🔍 Encontrados {len(arquivos)} arquivo(s) na entrada para processar...")
            for arquivo in arquivos:
                log_monitor(f"⚙️ Processando arquivo existente: {arquivo.name}")
                time.sleep(1)
                processar_arquivo(arquivo)
    
    log_monitor("🚀 Iniciando Arquivista Digital Inteligente da Cetti V2...")
    varrer_arquivos_existentes()
    
    # O polling é mais estável em pastas sincronizadas pelo Drive no Windows.
    observer = PollingObserver()
    observer.schedule(Handler(), str(ENTRADA), recursive=False)
    observer.start()
    log_monitor("👁️ Monitor aguardando novos arquivos...")

    try:
        chatbot()
    except KeyboardInterrupt:
        observer.stop()
    observer.join()