import os
import shutil
import time
import json
from importlib.metadata import PackageNotFoundError, version as package_version
import google.genai as genai
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

# ========================================================
# ALTERAÇÃO 1: Verificação de Versão da Biblioteca
# ========================================================
try:
    SDK_VERSION = package_version("google-genai")
except PackageNotFoundError:
    SDK_VERSION = "desconhecida"

print(f"🚀 Iniciando Cetti Organizador... (Versão SDK: {SDK_VERSION})")

def carregar_api_key():
    load_dotenv(override=True)

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
    print("❌ ERRO: defina GEMINI_API_KEY no arquivo .env ou na variável de ambiente.")
    raise SystemExit(1)

try:
    client = genai.Client(api_key=api_key)
    modelo_gemini = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
except Exception as e:
    print(f"❌ ERRO ao configurar o Gemini: {e}")
    print("💡 Verifique se a chave GEMINI_API_KEY está correta e ativa no Google AI Studio.")
    raise SystemExit(1)

# Configurações de Caminho
BASE_PATH = "G:/My Drive/Cetti_Organizador"
INPUT_DIR = os.path.join(BASE_PATH, "0_ENTRADA")
EXTENSOES_PERMITIDAS = ('.pdf', '.doc', '.docx', '.xls', '.xlsx', '.jpg', '.jpeg', '.png', '.txt')

PROMPT_SISTEMA = """
Você é um assistente jurídico especializado em triagem.
Analise o conteúdo do arquivo e identifique:
1. Nome completo do Advogado responsável.
2. Nome completo do Cliente.
3. Tipo exato do documento (ex: Petição Inicial, RG, Comprovante de Residência, Contrato Honorários).

RETORNE APENAS um JSON puro (sem markdown):
- Se conseguir identificar, use o nome exato
- Se NÃO conseguir identificar, use exatamente: "DESCONHECIDO"
- Nunca retorne vazio, nunca retorne "NOME_OU_DESCONHECIDO", sempre preencha com o nome ou "DESCONHECIDO"

Exemplo:
{"advogado": "João Silva", "cliente": "Maria Santos", "tipo": "Petição Inicial"}
ou
{"advogado": "DESCONHECIDO", "cliente": "DESCONHECIDO", "tipo": "OUTROS"}
"""

class CettiHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            self.processar_lote()

    def processar_lote(self):
        arquivos = [os.path.join(INPUT_DIR, f) for f in os.listdir(INPUT_DIR) 
                   if f.lower().endswith(EXTENSOES_PERMITIDAS)]
        
        # Processando 5 por lote conforme solicitado
        for file_path in arquivos[:5]:
            self.executar_ia(file_path)
            time.sleep(5) 

    def executar_ia(self, file_path):
        nome_arquivo = os.path.basename(file_path)
        print(f"\n--- Processando: {nome_arquivo} ---")
        
        try:
            # ========================================================
            # ALTERAÇÃO 2: Bloco de Upload Robusto com Tratamento de Erro
            # ========================================================
            print(f"📤 Fazendo upload para análise...")
            
            try:
                doc_ia = client.files.upload(file=file_path)
            except Exception as e:
                if eh_erro_autenticacao_ou_servico(e):
                    print("❌ ERRO ao fazer upload no Gemini: a chave foi rejeitada ou o serviço respondeu com falha.")
                    print("💡 Verifique se a chave pertence ao projeto correto, se a API Gemini está habilitada e se o modelo está disponível.")
                    return
                print(f"❌ ERRO no upload para o Gemini: {e}")
                return

            # Aguarda o processamento no servidor do Google
            while getattr(doc_ia, "state", None) and doc_ia.state.name == "PROCESSING":
                print("⏳ IA processando arquivo...", end="\r")
                time.sleep(2)
                doc_ia = client.files.get(name=doc_ia.name)

            if getattr(doc_ia, "state", None) and doc_ia.state.name == "FAILED":
                print("❌ IA falhou ao ler este arquivo.")
                return

            try:
                response = client.models.generate_content(
                    model=modelo_gemini,
                    contents=[PROMPT_SISTEMA, doc_ia],
                )
            except Exception as e:
                if eh_erro_autenticacao_ou_servico(e):
                    print("❌ ERRO ao solicitar análise ao Gemini: autenticação rejeitada ou serviço indisponível.")
                    print("💡 Se a chave estiver correta, teste outro modelo em GEMINI_MODEL ou verifique o status da API no projeto.")
                    return
                print(f"❌ ERRO ao solicitar análise ao Gemini: {e}")
                return
            
            # Limpeza de resposta para garantir JSON puro
            json_str = response.text.replace("```json", "").replace("```", "").strip()
            data = json.loads(json_str)

            adv = data.get("advogado", "DESCONHECIDO")
            cli = data.get("cliente", "DESCONHECIDO")
            tipo = data.get("tipo", "OUTROS")

            # Fallback Humano no Terminal
            if adv == "DESCONHECIDO" or cli == "DESCONHECIDO":
                print(f"⚠️ IA com dúvida para: {nome_arquivo}")
                if adv == "DESCONHECIDO": adv = input("Digite o Nome do ADVOGADO: ")
                if cli == "DESCONHECIDO": cli = input("Digite o Nome do CLIENTE: ")
            else:
                print(f"✅ IA Identificou: {cli} (Adv: {adv})")

            # Organização de Pastas
            adv, cli = adv.strip().upper(), cli.strip().upper()
            pasta_destino = os.path.join(BASE_PATH, adv, cli, tipo.strip().capitalize())
            
            os.makedirs(pasta_destino, exist_ok=True)
            
            # Movimentação Final com Retry (Caso o Drive ainda esteja sincronizando)
            try:
                shutil.move(file_path, os.path.join(pasta_destino, nome_arquivo))
                print(f"📂 Organizado em: {pasta_destino}")
            except PermissionError:
                print("⏳ Arquivo em uso pelo Google Drive. Tentando novamente em 5s...")
                time.sleep(5)
                shutil.move(file_path, os.path.join(pasta_destino, nome_arquivo))

        except Exception as e:
            print(f"❌ Erro crítico: {e}")

if __name__ == "__main__":
    if not os.path.exists(INPUT_DIR): os.makedirs(INPUT_DIR)
    
    handler = CettiHandler()
    observer = Observer()
    observer.schedule(handler, INPUT_DIR, recursive=False)
    observer.start()
    
    print(f"📂 Monitorando entrada: {INPUT_DIR}")
    handler.processar_lote()
    
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()