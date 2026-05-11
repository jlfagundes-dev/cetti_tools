"""
Módulo compartilhado de logging entre o monitor e o Streamlit.
"""
from pathlib import Path
from datetime import datetime


LOG_FILE = Path(__file__).parent / "cetti_monitor.log"


def log_monitor(mensagem: str):
    """Escreve mensagem no arquivo de log compartilhado com timestamp."""
    timestamp = datetime.now().strftime("%H:%M:%S")
    msg_formatada = f"[{timestamp}] {mensagem}"
    
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg_formatada + "\n")
    
    print(msg_formatada)


def ler_logs_recentes(quantidade: int = 10) -> list[str]:
    """Lê os últimos N logs do arquivo."""
    if not LOG_FILE.exists():
        return []
    
    logs = []
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        linhas = f.readlines()
        for linha in linhas[-quantidade:]:
            linha = linha.strip()
            if linha:
                logs.append(linha)
    
    return logs


def limpar_logs():
    """Limpa o arquivo de logs."""
    if LOG_FILE.exists():
        LOG_FILE.unlink()
