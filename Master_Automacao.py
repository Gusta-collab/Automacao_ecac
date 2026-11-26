# ─────────────────────────────────────────────────────────────────
# Automação fiscal e-CAC
# ─────────────────────────────────────────────────────────────────

from tkinter import messagebox, filedialog
import customtkinter as ctk
import os
import shutil
import threading
import time
import datetime
import random
import subprocess
import base64
import re
import json
import tempfile
import unicodedata
import glob
import filecmp
from typing import Any
import requests
import ctypes
import socket
from pathlib import Path
import datetime as dt
from urllib.parse import urlsplit

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import (
    TimeoutException, StaleElementReferenceException, NoSuchFrameException,
    NoSuchWindowException, ElementClickInterceptedException,
)


# ─────────────────────────────────────────────────────────────────
# TRAVA DE INSTÂNCIA ÚNICA (MUTEX)
# ─────────────────────────────────────────────────────────────────
_app_mutex = None


def garantir_instancia_unica():
    global _app_mutex
    _app_mutex = ctypes.windll.kernel32.CreateMutexW(
        None, False, "Automacao_Fiscal_Publica_Mutex"
    )
    if ctypes.windll.kernel32.GetLastError() == 183:
        ctypes.windll.user32.MessageBoxW(
            0,
            "O programa já está aberto ou há um processo fantasma travado.\n\nAbra o 'Gerenciador de Tarefas' do Windows e encerre o programa (ou reinicie o PC) e tente novamente.",
            "Aviso de Segurança",
            0x10,
        )
        os._exit(0)


garantir_instancia_unica()

# ─────────────────────────────────────────────────────────────────
# CONFIGURAÇÕES — GERENCIADOR JSON
# ─────────────────────────────────────────────────────────────────
DIRETORIO_CONFIG = os.path.join(
    os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Automacao_Fiscal"
)
ARQUIVO_CONFIG = os.path.join(DIRETORIO_CONFIG, "config.json")


def carregar_config():
    """Carrega configurações salvas ou aplica os padrões."""
    pasta_temp_padrao = os.path.join(
        os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
        "Automacao_Fiscal",
        "temp_downloads",
    )

    config_padrao = {
        "pasta_temp": pasta_temp_padrao,
        "caminho_copypasta": "",
        "pasta_padrao_clientes": "",
    }

    if os.path.exists(ARQUIVO_CONFIG):
        try:
            with open(ARQUIVO_CONFIG, "r", encoding="utf-8") as f:
                config_salva = json.load(f)
                config_padrao.update(config_salva)
        except Exception:
            pass

    os.makedirs(config_padrao["pasta_temp"], exist_ok=True)
    try:
        subprocess.run(["attrib", "+H", config_padrao["pasta_temp"]], check=False)
    except Exception:
        pass

    return config_padrao


def salvar_config(novas_configs):
    """Salva configurações no arquivo oculto."""
    pasta_destino = os.path.dirname(ARQUIVO_CONFIG)
    os.makedirs(pasta_destino, exist_ok=True)
    try:
        subprocess.run(["attrib", "+H", pasta_destino], check=False)
    except Exception:
        pass

    with open(ARQUIVO_CONFIG, "w", encoding="utf-8") as f:
        json.dump(novas_configs, f, indent=4)


CONFIG_APP = carregar_config()

# ─────────────────────────────────────────────────────────────────
# CONSTANTES E DICIONÁRIOS
# ─────────────────────────────────────────────────────────────────
ANO_INICIO = 2021
PORTA_DEBUG = 9222
HOST_ECAC = "cav.receita.fazenda.gov.br"

NOME_PASTA_DOCUMENTOS = "DOCUMENTOS"
NOMES_PASTA_DOCUMENTOS_ACEITOS = ("documentos", "documentacao")

SUBPASTA_DCTF = "dctf"
SUBPASTA_DCTFWEB = "dctf-web"
SUBPASTA_PERDCOMP = "PER-DCOMP"
SUBPASTA_PGDAS = "PGDAS"
SUBPASTA_DARF = "Darf"



DICIONARIO_CODIGOS = {
    "2172": "Cofins - Contribuição para Financiamento Seguridade Social - Presumido ou Real",
    "5856": "Cofins Não-Cumulativa - Real",
    "6012": "CSLL - Demais PJ que Apuram o IRPJ com Base em Lucro Real - Balanço Trimestral",
    "2484": "CSLL - Demais PJ que Apuram o IRPJ com base em Lucro Real - Estimativa Mensal",
    "2372": "CSLL - PJ que Apuram o IRPJ com Base em Lucro Presumido ou Arbitrado",
    "2089": "IRPJ - Lucro Presumido",
    "5993": "IRPJ - Optantes pela Apuracao com Base no Lucro Real - Estimativa Mensal",
    "3373": "IRPJ - PJ Não Obrigadas ao Lucro Real - Balanço Trimestral",
    "2362": "IRPJ- PJ Obrigadas ao Lucro Real - Entidades Não Financeiras - Estimativa Mensal",
    "0220": "IRPJ-PJ Obrigadas ao Lucro Real - Entidades não Financeiras - Balanço Trimestral",
    "8109": "PIS - Faturamento - Presumido ou Real",
    "6912": "PIS - Não Cumulativo - Real",
}

CODIGOS_RECEITA = list(DICIONARIO_CODIGOS.keys())

CHROME_EXE = os.path.join(
    os.environ.get("PROGRAMFILES", "C:\\Program Files"),
    "Google",
    "Chrome",
    "Application",
    "chrome.exe",
)
if not os.path.exists(CHROME_EXE):
    CHROME_EXE = os.path.join(
        os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)"),
        "Google",
        "Chrome",
        "Application",
        "chrome.exe",
    )

pasta_cliente = None
criacao_pasta_em_andamento = False
driver_global = None
deve_parar = False
ocupado_capturando = False
keep_alive_ativo = False
data_abertura_atual = "Não informada"
data_fim_simples_global = None

tipos_perdcomp_selecionados = {}
modulos_selecionados_vars = {}
MODULOS_CAPTACAO_LOCAL = ("DCTF Normal", "PER/DCOMP", "PGDAS", "DCTF-Web")


root: Any = None
entry_nome_cliente: Any = None
label_pasta: Any = None
btn_abrir_chrome: Any = None
btn_iniciar: Any = None
btn_reiniciar: Any = None
txt_log: Any = None
label_status: Any = None
execucao_em_andamento = False

EXT_DOWNLOAD_INCOMPLETO = (".crdownload", ".tmp")
ARQUIVOS_IGNORADOS_TEMP = {"desktop.ini", "thumbs.db"}


# ─────────────────────────────────────────────────────────────────
# SUPORTE E CONTROLE DE SESSÃO (KEEP-ALIVE 24H)
# ─────────────────────────────────────────────────────────────────
def pausa(minimo=0.8, maximo=1.5):
    time.sleep(random.uniform(minimo, maximo))


def verificar_parada():
    if deve_parar:
        raise Exception("Execução interrompida pelo usuário.")


def restaurar_janela(driver, handle_esperado=None):
    handles = driver.window_handles
    if not handles:
        raise Exception("Nenhuma janela do navegador está disponível.")
    if handle_esperado and handle_esperado in handles:
        driver.switch_to.window(handle_esperado)
        return handle_esperado
    driver.switch_to.window(handles[0])
    return handles[0]


def status(texto, cor="gray"):
    if root and label_status:
        root.after(0, lambda: label_status.configure(text=texto, text_color=cor))


def log(texto):
    print(texto)
    if root and txt_log:
        root.after(
            0,
            lambda: _inserir_log(
                f"{datetime.datetime.now().strftime('%H:%M:%S')} - {texto}"
            ),
        )


def _inserir_log(texto):
    txt_log.configure(state="normal")
    txt_log.insert("end", texto + "\n")
    txt_log.see("end")
    txt_log.configure(state="disabled")


def iniciar_keep_alive(driver):
    global keep_alive_ativo
    if keep_alive_ativo:
        return
    keep_alive_ativo = True
    threading.Thread(target=manter_sessao_ativa, args=(driver,), daemon=True).start()


def manter_sessao_ativa(driver):
    global deve_parar, ocupado_capturando
    log("⏱️ Sistema Keep-Alive 24h ativado.")
    tempo_passado = 0
    while not deve_parar:
        time.sleep(5)
        tempo_passado += 5
        if tempo_passado >= 600:
            tempo_passado = 0
            if not ocupado_capturando:
                try:
                    aba_atual = driver.current_window_handle
                    driver.switch_to.default_content()
                    btn_inicio = driver.find_elements(
                        By.XPATH, "//a[contains(text(), 'Início')]"
                    )
                    if btn_inicio:
                        driver.execute_script("arguments[0].click();", btn_inicio[0])
                        log("🔄 Keep-Alive: Sessão do eCAC renovada com sucesso.")
                    driver.switch_to.window(aba_atual)
                except Exception:
                    pass


def pausa_longa_com_keep_alive(segundos):
    global ocupado_capturando
    minutos = segundos // 60
    log(f"⏳ Pausando captação por {minutos} min devido à indisponibilidade.")
    ocupado_capturando = False
    tempo_esperado = 0
    while tempo_esperado < segundos:
        verificar_parada()
        time.sleep(5)
        tempo_esperado += 5
    ocupado_capturando = True
    log("▶ Fim da pausa. Retomando processamento...")


def _chrome_debug_disponivel(porta=PORTA_DEBUG):
    try:
        resposta = requests.get(f"http://127.0.0.1:{porta}/json/version", timeout=2)
        return resposta.ok and "Browser" in resposta.json()
    except (requests.RequestException, ValueError):
        return False


def abrir_chrome_debug():
    """Abre o Chrome para o usuário autenticar-se sem controle do Selenium."""
    try:
        status("Abrindo Chrome para login manual...", "blue")
        perfil = os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
            "Automacao_Fiscal_Chrome_Profile",
        )
        if not _chrome_debug_disponivel():
            if not os.path.isfile(CHROME_EXE):
                raise RuntimeError("Chrome não encontrado no caminho configurado.")
            subprocess.Popen([
                CHROME_EXE,
                f"--remote-debugging-port={PORTA_DEBUG}",
                f"--user-data-dir={perfil}",
                "--no-first-run",
                "--no-default-browser-check",
                "https://cav.receita.fazenda.gov.br/autenticacao/login",
            ])
            for _ in range(20):
                if _chrome_debug_disponivel():
                    break
                time.sleep(0.5)
        if not _chrome_debug_disponivel():
            raise RuntimeError("Chrome não iniciou a sessão de depuração. Feche o perfil da automação e tente novamente.")
        log("Chrome aberto. Faça a autenticação manual no e-CAC e depois clique em Iniciar.")
        status("Aguardando login manual no e-CAC", "green")
    except Exception as erro:
        log(f"Erro Chrome: {str(erro).split('Stacktrace:')[0].strip()}")
        status("Erro de Conexão", "red")


def _url_do_ecac(url):
    try:
        partes = urlsplit(url)
        return partes.scheme == "https" and partes.hostname == HOST_ECAC
    except ValueError:
        return False


def conectar_chrome_autenticado():
    """Conecta o Selenium somente após o login manual no e-CAC."""
    global driver_global
    if driver_global is not None:
        try:
            if driver_global.window_handles:
                return True
        except Exception:
            driver_global = None
    if not _chrome_debug_disponivel():
        messagebox.showwarning("Chrome", "Abra o Chrome pelo aplicativo e faça o login no e-CAC.")
        return False
    candidato = None
    try:
        opcoes = Options()
        opcoes.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORTA_DEBUG}")
        candidato = webdriver.Chrome(options=opcoes)
        for aba in candidato.window_handles:
            try:
                candidato.switch_to.window(aba)
                url = candidato.current_url.lower()
                if _url_do_ecac(url) and not any(
                    trecho in url for trecho in ("autenticacao", "login")
                ):
                    os.makedirs(CONFIG_APP["pasta_temp"], exist_ok=True)
                    candidato.execute_cdp_cmd("Browser.setDownloadBehavior", {
                        "behavior": "allow",
                        "downloadPath": os.path.abspath(CONFIG_APP["pasta_temp"]),
                        "eventsEnabled": True,
                    })
                    driver_global = candidato
                    log("Sessão autenticada do e-CAC conectada.")
                    return True
            except Exception:
                continue
        messagebox.showwarning(
            "e-CAC", "Conclua o login manual no e-CAC antes de clicar em Iniciar."
        )
    except Exception as erro:
        log(f"Não foi possível conectar ao Chrome: {str(erro).split('Stacktrace:')[0].strip()}")
        status("Erro de Conexão", "red")
    return False


def obter_pasta_documentos(base=None, criar=True):
    base = base or pasta_cliente
    if not base:
        raise Exception("Pasta do cliente não definida.")

    def _norm(texto):
        texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode()
        return texto.lower().strip()

    try:
        existentes = {
            _norm(nome): os.path.join(base, nome)
            for nome in os.listdir(base)
            if os.path.isdir(os.path.join(base, nome))
        }
    except OSError:
        existentes = {}

    achadas = [n for n in NOMES_PASTA_DOCUMENTOS_ACEITOS if n in existentes]
    if achadas:
        return existentes[achadas[0]]

    caminho = os.path.join(base, NOME_PASTA_DOCUMENTOS)
    if criar:
        os.makedirs(caminho, exist_ok=True)
    return caminho


def garantir_pasta_ano(tipo_declaracao, ano):
    tipo_upper = tipo_declaracao.upper()
    if "DCTF-WEB" in tipo_upper:
        pasta_modulo = SUBPASTA_DCTFWEB
    elif "DCTF" in tipo_upper:
        pasta_modulo = SUBPASTA_DCTF
    elif "PGDAS" in tipo_upper:
        pasta_modulo = SUBPASTA_PGDAS
    else:
        pasta_modulo = tipo_declaracao.replace("/", "-").lower()

    caminho = os.path.join(obter_pasta_documentos(pasta_cliente), pasta_modulo, str(ano))
    os.makedirs(caminho, exist_ok=True)
    return caminho


def pasta_temporaria():
    caminho = CONFIG_APP["pasta_temp"]
    os.makedirs(caminho, exist_ok=True)
    return caminho


def limpar_pasta_temp(pasta_temp):
    try:
        if os.path.exists(pasta_temp) and not os.listdir(pasta_temp):
            os.rmdir(pasta_temp)
    except Exception:
        pass


def manter_ecac_logado():
    """Roda em segundo plano e clica no botão Home a cada 5 minutos para evitar o logout do e-CAC."""
    global driver_global, automacao_em_andamento, deve_parar
    
    while True:
        time.sleep(300)  # Espera 5 minutos (300 segundos)
        
        # Só tenta clicar se o navegador estiver aberto e NENHUMA automação estiver rodando
        if driver_global is not None and not automacao_em_andamento and not deve_parar:
            try:
                # Salva a aba atual para não perder o foco
                aba_atual = driver_global.current_window_handle
                driver_global.switch_to.default_content()
                
                # Procura o botão Home na raiz
                btn_home = driver_global.find_elements(By.ID, "linkHome")
                
                # Se não achou na raiz, procura dentro dos iframes
                if not btn_home:
                    for iframe in driver_global.find_elements(By.TAG_NAME, "iframe"):
                        try:
                            driver_global.switch_to.default_content()
                            driver_global.switch_to.frame(iframe)
                            btn_home = driver_global.find_elements(By.ID, "linkHome")
                            if btn_home:
                                break
                        except:
                            pass
                
                # Clica se o botão estiver visível e habilitado
                if btn_home and btn_home[0].is_displayed():
                    driver_global.execute_script("arguments[0].click();", btn_home[0])
                    log("🔄 [Anti-Timeout] Ocioso há 5 min: Clique em 'Home' realizado para manter a sessão.")
                
                # Devolve o foco original ao navegador
                driver_global.switch_to.default_content()
                driver_global.switch_to.window(aba_atual)
                
            except Exception:
                pass  # Ignora erros silenciosamente para não travar o programa


def parar_e_reiniciar():
    global deve_parar
    resposta = messagebox.askyesno(
        "Reiniciar",
        "Tem certeza que deseja interromper a busca atual e reiniciar o painel?",
    )
    if not resposta:
        return

    status("Interrompendo a busca...", "orange")
    deve_parar = True

    txt_log.configure(state="normal")
    txt_log.delete("1.0", "end")
    txt_log.insert(
        "end",
        "── Busca Interrompida e Painel Reiniciado ──\nO seu navegador continua aberto e logado.\nAjuste as opções e inicie uma nova busca quando quiser.\n",
    )
    txt_log.configure(state="disabled")

    btn_iniciar.configure(state="normal")
    btn_abrir_chrome.configure(state="normal")
    btn_reiniciar.configure(state="disabled")
    label_status.configure(text="Aguardando nova execução...", text_color="gray")


def substituir_arquivo(origem, destino):
    if os.path.abspath(origem) == os.path.abspath(destino):
        return
    tmp = destino + ".tmp"
    try:
        if os.path.exists(tmp):
            os.remove(tmp)
        shutil.move(origem, tmp)
        os.replace(tmp, destino)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise


def gravar_pdf_substituindo(destino, dados_bytes):
    tmp = destino + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(dados_bytes)
        os.replace(tmp, destino)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise


def _tamanho_seguro(caminho):
    try:
        return os.path.getsize(caminho)
    except Exception:
        return 0


# ─────────────────────────────────────────────────────────────────
def verificar_indisponibilidade(driver):
    try:
        xpath_msg = "//h3[contains(text(), 'SISTEMA INDISPONÍVEL')]"
        driver.switch_to.default_content()
        msg_erro = driver.find_elements(By.XPATH, xpath_msg)
        if not msg_erro:
            for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe)
                    msg_erro = driver.find_elements(By.XPATH, xpath_msg)
                    if msg_erro:
                        break
                except Exception:
                    pass
        if msg_erro and msg_erro[0].is_displayed():
            log("⚠️ ATENÇÃO: Sistema fora do ar detectado!")
            driver.switch_to.default_content()
            btn_home = driver.find_elements(By.ID, "linkHome")
            if btn_home:
                driver.execute_script("arguments[0].click();", btn_home[0])
            return True
    except Exception:
        pass
    return False


def voltar_para_home_ecac(driver):
    try:
        driver.switch_to.default_content()
        btn_home = driver.find_elements(By.ID, "linkHome")
        if not btn_home:
            for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe)
                    btn_home = driver.find_elements(By.ID, "linkHome")
                    if btn_home:
                        break
                except Exception:
                    pass
        if btn_home:
            driver.execute_script("arguments[0].click();", btn_home[0])
            time.sleep(1.5)
    except Exception:
        pass

def focar_aba_principal_ecac(driver):
    """Encontra e foca a guia principal do portal e-CAC (ignorando guias secundárias)."""
    for aba in driver.window_handles:
        try:
            driver.switch_to.window(aba)
            url = driver.current_url.lower()
            if _url_do_ecac(url) and "dctfweb" not in url:
                return aba
        except Exception:
            continue
    return None


def fechar_abas_dctfweb(driver, aba_principal=None):
    """Fecha todas as guias da DCTF-Web para não misturar CNPJs e devolve o foco à guia principal."""
    for aba in list(driver.window_handles):
        try:
            driver.switch_to.window(aba)
            url = driver.current_url.lower()
            titulo = driver.title.lower()
            if "dctfweb" in url or "dctf web" in titulo:
                # Só fecha se houver mais de uma guia aberta no navegador
                if len(driver.window_handles) > 1:
                    driver.close()
                    log("🔒 Guia da DCTF-Web encerrada para evitar conflito de CNPJ.")
        except Exception:
            continue

    # Devolve o foco para a guia principal do e-CAC
    if aba_principal and aba_principal in driver.window_handles:
        driver.switch_to.window(aba_principal)
    else:
        focar_aba_principal_ecac(driver)


# ─────────────────────────────────────────────────────────────────
# MÓDULO 1: DCTF NORMAL
# ─────────────────────────────────────────────────────────────────
class DctfIndisponivel(RuntimeError):
    """Indisponibilidade temporária, sem concluir a captação da DCTF."""


def navegar_para_dctf(driver):
    espera = WebDriverWait(driver, 15)
    log("Navegando para DCTF Normal...")
    try:
        driver.switch_to.default_content()
        menu = espera.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//a[contains(normalize-space(.), 'Declarações e Demonstrativos')]")
            )
        )
        driver.execute_script("arguments[0].click();", menu)
        pausa()

        link_dctf = espera.until(
            EC.element_to_be_clickable(
                (By.XPATH, "//a[contains(normalize-space(.), 'Extrato') and contains(normalize-space(.), 'DCTF')]")
            )
        )
        abas_antes = set(driver.window_handles)
        driver.execute_script("arguments[0].click();", link_dctf)

        try:
            WebDriverWait(driver, 8).until(
                lambda d: len(d.window_handles) > len(abas_antes)
            )
            nova_aba = (set(driver.window_handles) - abas_antes).pop()
            driver.switch_to.window(nova_aba)
        except TimeoutException:
            pass

        xpath_btn = "//input[contains(@value, 'Consultar')] | //button[contains(text(), 'Consultar')]"
        for _ in range(8):
            if verificar_indisponibilidade(driver):
                raise DctfIndisponivel("DCTF indisponível no momento; captação pendente.")
            driver.switch_to.default_content()
            botoes = driver.find_elements(By.XPATH, xpath_btn)
            if botoes:
                driver.execute_script("arguments[0].click();", botoes[0])
                return True
            for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
                try:
                    driver.switch_to.default_content()
                    driver.switch_to.frame(iframe)
                    botoes = driver.find_elements(By.XPATH, xpath_btn)
                    if botoes:
                        driver.execute_script("arguments[0].click();", botoes[0])
                        return True
                except Exception:
                    pass
            time.sleep(1.2)
        log("✘ Tela de consulta da DCTF Normal não carregou.")
        return False
    except DctfIndisponivel:
        raise
    except Exception:
        return False


DCTF_XPATH_LINHAS = (
    "//table[@id='tbDeclaracoes']//tr[count(td) >= 8]"
)


def aguardar_documentos_dctf(driver, timeout=120):
    """Reconhece a tabela HTML pronta, com documentos ou vazia, sem pausa fixa."""
    limite = time.monotonic() + timeout
    espera_registrada = False

    def localizar(nivel=0):
        avisos = driver.find_elements(
            By.XPATH, "//h3[contains(normalize-space(.), 'SISTEMA INDISPONÍVEL')]"
        )
        for aviso in avisos:
            if aviso.is_displayed():
                mensagem = " ".join(aviso.text.split())
                raise DctfIndisponivel(f"DCTF indisponível: {mensagem}")
        tabelas = driver.find_elements(By.ID, "tbDeclaracoes")
        if tabelas and tabelas[0].is_displayed():
            cabecalhos = tabelas[0].find_elements(By.XPATH, ".//tr/th")
            if len(cabecalhos) >= 8 and driver.execute_script("return document.readyState") == "complete":
                return driver.find_elements(By.XPATH, DCTF_XPATH_LINHAS)
        if nivel < 4:
            for frame in driver.find_elements(By.CSS_SELECTOR, "iframe, frame"):
                driver.switch_to.frame(frame)
                linhas = localizar(nivel + 1)
                if linhas is not None:
                    return linhas  # Mantém o contexto da tabela encontrada.
                driver.switch_to.parent_frame()
        return None  # Diferente de []: tabela ainda não encontrada/carregada.

    while time.monotonic() < limite:
        verificar_parada()
        try:
            # Ao voltar de um PDF, o frame da tabela pode já estar selecionado.
            linhas = localizar()
            if linhas is not None:
                return linhas
            driver.switch_to.default_content()
            linhas = localizar()
            if linhas is not None:
                return linhas
        except DctfIndisponivel:
            raise
        except Exception:
            # A navegação pode substituir o frame enquanto a consulta carrega.
            driver.switch_to.default_content()
        if not espera_registrada:
            log("DCTF: verificando o HTML até a tabela de declarações estar pronta...")
            espera_registrada = True
        time.sleep(0.2)
    raise RuntimeError(
        "A lista de documentos da DCTF não carregou no prazo; "
        "módulo pendente, sem avançar para PER/DCOMP neste CNPJ."
    )


def processar_dctf_normal(driver, pasta_temp, tipo_declaracao="DCTF Normal"):
    log("\n── DCTF NORMAL " + "─" * 30)
    linhas = aguardar_documentos_dctf(driver)

    if not linhas:
        log("✔ Tabela DCTF carregada: nenhuma declaração disponível.")
        return 0, set()

    log(f"✔ Tabela detectada com {len(linhas)} linha(s).")
    arquivos_baixados = 0
    meses_sucesso = set()

    for i in range(len(linhas)):
        verificar_parada()
        try:
            linhas_refresh = driver.find_elements(By.XPATH, DCTF_XPATH_LINHAS)
            if i >= len(linhas_refresh):
                break
            linha = linhas_refresh[i]
            colunas = linha.find_elements(By.TAG_NAME, "td")
            if len(colunas) < 8:
                continue

            texto_periodo = colunas[3].text.strip()
            texto_status_limpo = colunas[6].text.strip().lower().replace(" ", "")

            try:
                _, mes_str, ano_str = colunas[4].text.strip().split("/")
                ano_linha, mes_linha = int(ano_str), int(mes_str)
            except ValueError:
                continue

            if ano_linha < ANO_INICIO or texto_status_limpo not in [
                "original/ativa",
                "retificadora/ativa",
            ]:
                continue

            candidatos = linha.find_elements(
                By.XPATH,
                ".//input[@type='button' and contains(@class,'print') and contains(@onclick,'selecionaServico')]",
            )
            if not candidatos:
                continue

            btn_download = candidatos[0]
            aba_original = driver.current_window_handle
            abas_antes = set(driver.window_handles)

            try:
                btn_download.click()
            except Exception:
                driver.execute_script("arguments[0].click();", btn_download)

            try:
                WebDriverWait(driver, 3).until(EC.alert_is_present())
                driver.switch_to.alert.accept()
            except TimeoutException:
                pass

            abriu_nova_aba = False
            try:
                WebDriverWait(driver, 15).until(
                    lambda d: len(d.window_handles) > len(abas_antes)
                )
                nova_aba = (set(driver.window_handles) - abas_antes).pop()
                driver.switch_to.window(nova_aba)
                abriu_nova_aba = True
            except TimeoutException:
                pass

            time.sleep(2.0)

            try:
                pdf_dict = driver.execute_cdp_cmd(
                    "Page.printToPDF", {"printBackground": True}
                )
                pasta_destino = garantir_pasta_ano(tipo_declaracao, ano_linha)
                nome_arquivo = f"{str(mes_linha).zfill(2)}-{ano_linha}.pdf"
                caminho_final = os.path.join(pasta_destino, nome_arquivo)

                gravar_pdf_substituindo(
                    caminho_final, base64.b64decode(pdf_dict["data"])
                )
                arquivos_baixados += 1
                meses_sucesso.add((ano_linha, mes_linha))
                log(f"    [✔] Salvo: {nome_arquivo}")
            except Exception as e_pdf:
                log(f"    [✘] Falha ao salvar PDF de {texto_periodo}: {e_pdf}")

            if abriu_nova_aba:
                try:
                    driver.close()
                except Exception:
                    pass
            restaurar_janela(driver, aba_original)

            aguardar_documentos_dctf(driver)
        except Exception as e:
            if "interrompida" in str(e).lower():
                raise e
            log(f"✘ Falha na captação da DCTF: {e}")
            raise

    return arquivos_baixados, meses_sucesso


# ─────────────────────────────────────────────────────────────────
# MÓDULO 2: DCTF-WEB
# ─────────────────────────────────────────────────────────────────
def localizar_tela_dctfweb(driver, timeout=8):
    limite = time.time() + timeout
    xpath_alvo = "//*[contains(text(), 'Data Transmissão Inicial')]"
    while time.time() < limite:
        verificar_parada()
        for aba in driver.window_handles:
            driver.switch_to.window(aba)
            if "dctfweb" in driver.current_url.lower() or "dctf web" in driver.title.lower():
                try:
                    driver.switch_to.default_content()
                    if driver.find_elements(By.XPATH, xpath_alvo):
                        return True
                    for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
                        try:
                            driver.switch_to.default_content()
                            driver.switch_to.frame(iframe)
                            if driver.find_elements(By.XPATH, xpath_alvo):
                                return True
                        except Exception:
                            pass
                except Exception:
                    pass
        time.sleep(0.5)
    return False


def navegar_para_dctf_web(driver):
    """
    Navega até o DCTF-Web de forma segura, garantindo que a nova aba
    seja aberta, focada e totalmente carregada.
    """
    espera = WebDriverWait(driver, 15)
    log("Navegando para DCTF-Web...")
    try:
        driver.switch_to.default_content()

        # 1. EXPANDIR O MENU
        try:
            menu_declaracoes = espera.until(
                EC.element_to_be_clickable(
                    (
                        By.XPATH,
                        "//a[contains(normalize-space(.), 'Declarações e Demonstrativos')]",
                    )
                )
            )
            # Tenta clique nativo primeiro; se falhar, vai via JS
            try:
                menu_declaracoes.click()
            except Exception:
                driver.execute_script("arguments[0].click();", menu_declaracoes)
            time.sleep(1)
        except Exception:
            pass  # Se o menu já estiver aberto ou visível, prossegue

        # Salva o estado atual (aba original)
        aba_original = driver.current_window_handle
        abas_antes = driver.window_handles

        # 2. LOCALIZAR O LINK
        xpath_link = "//a[contains(text(), 'Assinar e Transmitir DCTFWeb')]"
        link_dctf_web = espera.until(EC.element_to_be_clickable((By.XPATH, xpath_link)))

        # Força a abertura abrindo o link diretamente se o clique normal falhar
        try:
            link_dctf_web.click()
        except Exception:
            # Fallback: obtém a URL do href e abre uma nova guia via script limpo
            url_href = link_dctf_web.get_attribute("href")
            if url_href and url_href != "#":
                driver.execute_script(f"window.open('{url_href}', '_blank');")
            else:
                driver.execute_script("arguments[0].click();", link_dctf_web)

        # 3. AGUARDA A ABERTURA DA NOVA ABA (Nativo do Selenium)
        log("Aguardando a abertura da aba do DCTF-Web...")
        try:
            espera.until(EC.new_window_is_opened(abas_antes))
        except Exception:
            raise Exception("A nova guia não foi aberta dentro do tempo limite (15s).")

        # Identifica e alterna para a nova aba
        abas_depois = driver.window_handles
        nova_aba = [aba for aba in abas_depois if aba not in abas_antes][0]
        driver.switch_to.window(nova_aba)
        log("✔ Nova guia do DCTF-Web identificada e focada.")

        # 4. AGUARDA O CARREGAMENTO COMPLETO DA PÁGINA DCTF-WEB
        # Espera que a URL mude/carregue e que um elemento do DCTFWeb apareça
        espera.until(lambda d: "dctf" in d.current_url.lower())
        espera.until(
            EC.presence_of_element_located(
                (By.XPATH, "//body[not(contains(@style, 'display: none'))]")
            )
        )

        # Verifica indisponibilidade antes de liberar o controle
        if verificar_indisponibilidade(driver):
            driver.close()
            driver.switch_to.window(aba_original)
            return False

        log("Aguardando os campos de consulta da DCTF-Web carregarem...")
        if not localizar_tela_dctfweb(driver, timeout=60):
            raise RuntimeError("Campos de consulta da DCTF-Web não carregaram.")
        return aba_original

    except Exception as e:
        log(f"Erro na navegação DCTF-Web: {e}")
        return False


def processar_dctf_web(driver, pasta_temp, tipo_declaracao="DCTF-Web"):
    log("\n── Iniciando Leitura DCTF-Web ──")
    ano_atual = datetime.date.today().year
    aba_original = driver.current_window_handle
    arquivos_baixados = 0
    meses_sucesso = set()
    os.makedirs(pasta_temp, exist_ok=True)

    driver.execute_cdp_cmd(
        "Browser.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": os.path.abspath(pasta_temp), "eventsEnabled": True},
    )

    def executar_download(periodo_guia, ano_pesquisa):
        try:
            try:
                ano_real = int(periodo_guia.split("/")[1].strip())
            except (IndexError, ValueError):
                ano_real = int(ano_pesquisa)

            pasta_final_ano = garantir_pasta_ano(tipo_declaracao, ano_real)
            for f in os.listdir(pasta_temp):
                try:
                    os.remove(os.path.join(pasta_temp, f))
                except Exception:
                    pass

            verificar_parada()
            menu_relatorios = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'Relatórios') or contains(text(), 'RELATÓRIOS')]")
                )
            )
            driver.execute_script("arguments[0].click();", menu_relatorios)
            time.sleep(0.3)

            submenu_decl = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'Declaração completa') or contains(text(), 'Completa')]")
                )
            )
            driver.execute_script("arguments[0].click();", submenu_decl)

            tempo_espera = 0
            arquivo_baixado = None
            while tempo_espera < 60:
                verificar_parada()
                arquivos = [
                    f
                    for f in os.listdir(pasta_temp)
                    if not f.endswith(EXT_DOWNLOAD_INCOMPLETO)
                ]
                if arquivos:
                    arquivo_baixado = arquivos[0]
                    time.sleep(0.4)
                    break
                time.sleep(0.5)
                tempo_espera += 1

            if arquivo_baixado:
                caminho_antigo = os.path.join(pasta_temp, arquivo_baixado)
                caminho_novo = os.path.join(pasta_final_ano, arquivo_baixado)
                substituir_arquivo(caminho_antigo, caminho_novo)
                return f"[Salvo: {arquivo_baixado}]"
            return "[Erro: Timeout no PDF]"
        except Exception as e_down:
            return f"[Erro Download: {str(e_down)}]"

    for ano in range(ANO_INICIO, ano_atual + 1):
        verificar_parada()
        log(f"\nFiltrando Data de Transmissão de {ano}...")
        data_inicial = f"01/01/{ano}"
        data_final = (
            datetime.date.today().strftime("%d/%m/%Y")
            if ano == ano_atual
            else f"01/12/{ano}"
        )

        try:
            if not localizar_tela_dctfweb(driver):
                continue

            input_data_ini = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'Data Transmissão Inicial')]/following::input[1]")
                )
            )
            input_data_fin = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//*[contains(text(), 'Data Transmissão Final')]/following::input[1]")
                )
            )

            input_data_ini.clear()
            input_data_ini.send_keys(data_inicial)
            input_data_fin.clear()
            input_data_fin.send_keys(data_final)

            btn_pesquisar = driver.find_element(
                By.XPATH, "//*[contains(translate(text(), 'PESQUISAR', 'pesquisar'), 'pesquisar')]"
            )
            driver.execute_script("arguments[0].click();", btn_pesquisar)

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "//table//tbody//tr"))
                )
                time.sleep(0.5)
            except TimeoutException:
                pass

            while True:
                idx = 0
                while True:
                    verificar_parada()
                    try:
                        linhas = driver.find_elements(By.XPATH, "//table//tbody//tr")
                        if idx >= len(linhas):
                            break
                        colunas = linhas[idx].find_elements(By.TAG_NAME, "td")
                        if len(colunas) < 10:
                            idx += 1
                            continue
                        periodo = colunas[0].text.strip()
                        if not periodo:
                            idx += 1
                            continue

                        candidatos_caixa = colunas[9].find_elements(
                            By.XPATH, ".//input[@type='checkbox']"
                        )
                        if not candidatos_caixa:
                            idx += 1
                            continue

                        checkbox = candidatos_caixa[0]
                        if not driver.execute_script("return arguments[0].checked;", checkbox):
                            driver.execute_script("arguments[0].click();", checkbox)
                            time.sleep(0.6)

                        botoes = linhas[idx].find_elements(
                            By.XPATH,
                            ".//a[contains(@class, 'image-tabela-visualizacao') or @title='Visualizar']",
                        )
                        if botoes:
                            abas_antes = set(driver.window_handles)
                            driver.execute_script("arguments[0].click();", botoes[0])
                            nova_aba = None
                            try:
                                WebDriverWait(driver, 3).until(
                                    lambda d: len(d.window_handles) > len(abas_antes)
                                )
                                nova_aba = (set(driver.window_handles) - abas_antes).pop()
                            except Exception:
                                pass

                            if nova_aba and nova_aba in driver.window_handles:
                                driver.switch_to.window(nova_aba)
                                status_down = executar_download(periodo, ano)
                                try:
                                    driver.close()
                                except Exception:
                                    pass
                                restaurar_janela(driver, aba_original)
                                localizar_tela_dctfweb(driver)
                            else:
                                status_down = executar_download(periodo, ano)
                                try:
                                    driver.execute_script("window.history.back();")
                                except Exception:
                                    pass
                                localizar_tela_dctfweb(driver)

                            if status_down.startswith("[Salvo"):
                                arquivos_baixados += 1
                                try:
                                    partes = periodo.split("/")
                                    meses_sucesso.add((int(partes[1].strip()), int(partes[0].strip())))
                                except Exception:
                                    pass
                            log(f"    -> Período: {periodo} | {status_down}")
                        idx += 1
                    except Exception as erro_loop:
                        if "interrompida" in str(erro_loop).lower():
                            raise erro_loop
                        idx += 1

                try:
                    xpath_next = "//img[contains(@class, 'image-paginacao-proxima') or contains(@id, 'imgNextPage')]"
                    botoes_next = driver.find_elements(By.XPATH, xpath_next)
                    clicou_proxima = False
                    for btn in botoes_next:
                        if btn.is_displayed():
                            classe_pai = (
                                btn.find_element(By.XPATH, "..").get_attribute("class") or ""
                            ).lower()
                            if "disabled" in classe_pai or "inativo" in classe_pai:
                                continue
                            tabela_antiga = driver.find_element(By.XPATH, "//table//tbody")
                            driver.execute_script("arguments[0].click();", btn)
                            try:
                                WebDriverWait(driver, 5).until(EC.staleness_of(tabela_antiga))
                                clicou_proxima = True
                                time.sleep(0.5)
                            except Exception:
                                pass
                            break
                    if not clicou_proxima:
                        break
                except Exception:
                    break
        except Exception as e:
            if "interrompida" in str(e).lower():
                raise e

    return arquivos_baixados, meses_sucesso


# ─────────────────────────────────────────────────────────────────
# MÓDULO 3: PER/DCOMP (DOWNLOAD DIRETO POR PASTA SEM PASTA TEMP)
# ─────────────────────────────────────────────────────────────────
def localizar_tela_perdcomp(driver):
    limite = time.time() + 8
    xpath_alvo = "//*[contains(text(), 'Documentos Entregues') or contains(text(), 'PER/DCOMP - Pedido Eletrônico')]"
    while time.time() < limite:
        verificar_parada()
        for aba in driver.window_handles:
            try:
                driver.switch_to.window(aba)
                driver.switch_to.default_content()
                if driver.find_elements(By.XPATH, xpath_alvo):
                    return True
                for iframe in driver.find_elements(By.TAG_NAME, "iframe"):
                    try:
                        driver.switch_to.default_content()
                        driver.switch_to.frame(iframe)
                        if driver.find_elements(By.XPATH, xpath_alvo):
                            return True
                    except Exception:
                        pass
            except Exception:
                continue
        time.sleep(0.5)
    return False


def navegar_para_perdcomp(driver):
    if localizar_tela_perdcomp(driver):
        if driver.find_elements(By.XPATH, "//select[contains(@id, 'tipoDocumento')] | //*[contains(text(), 'Tipo de Documento')]/following::select[1]"):
            return True
    log("Navegando para PER/DCOMP WEB...")
    try:
        driver.switch_to.default_content()
        btn_rest = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Restituição e Compensação')]"))
        )
        driver.execute_script("arguments[0].click();", btn_rest)
        link_acessar = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(@href, 'Aplicacao.aspx?id=10006')]"))
        )
        driver.execute_script("arguments[0].click();", link_acessar)
        time.sleep(3)

        driver.switch_to.default_content()
        try:
            iframe_app = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "frmApp"))
            )
            driver.switch_to.frame(iframe_app)
        except Exception:
            pass

        menu_vis = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Visualizar')]//ancestor::a"))
        )
        driver.execute_script("arguments[0].click();", menu_vis)

        link_docs = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.XPATH, "//a[contains(text(), 'Documentos Entregues')]"))
        )
        driver.execute_script("arguments[0].click();", link_docs)
        log("Aguardando a tela de documentos PER/DCOMP carregar...")
        WebDriverWait(driver, 60).until(EC.presence_of_element_located((
            By.XPATH, "//select[contains(@id, 'tipoDocumento')] | //*[contains(text(), 'Tipo de Documento')]/following::select[1]"
        )))
        return True
    except Exception as e:
        log(f"Erro na navegação PER-DCOMP: {e}")
        return False


def listar_pasta_direta(pasta):
    prontos, em_andamento = set(), set()
    if not os.path.isdir(pasta):
        return prontos, em_andamento

    for nome in os.listdir(pasta):
        nome_l = nome.lower()
        if nome_l in ARQUIVOS_IGNORADOS_TEMP or nome.startswith("~$"):
            continue
        caminho = os.path.join(pasta, nome)
        if not os.path.isfile(caminho):
            continue
        if nome_l.endswith(EXT_DOWNLOAD_INCOMPLETO):
            em_andamento.add(nome)
        else:
            prontos.add(nome)
    return prontos, em_andamento


def aguardar_downloads_na_pasta(pasta_destino, qtd_antes, qtd_clicados, timeout_total=180):
    inicio = time.time()
    alvo = qtd_antes + qtd_clicados
    ultima_atividade = inicio
    estado_ant = None

    while time.time() - inicio < timeout_total:
        verificar_parada()
        prontos, em_andamento = listar_pasta_direta(pasta_destino)
        tam_andamento = sum(
            _tamanho_seguro(os.path.join(pasta_destino, f)) for f in em_andamento
        )
        estado_atual = (len(prontos), len(em_andamento), tam_andamento)

        if estado_atual != estado_ant:
            estado_ant = estado_atual
            ultima_atividade = time.time()

        if not em_andamento and len(prontos) >= alvo:
            time.sleep(1.0)
            return len(prontos) - qtd_antes

        if em_andamento:
            time.sleep(1.0)
            continue

        if time.time() - ultima_atividade >= 8:
            return max(0, len(prontos) - qtd_antes)

        time.sleep(1.0)

    prontos, _ = listar_pasta_direta(pasta_destino)
    return max(0, len(prontos) - qtd_antes)


def processar_perdcomp(driver, pasta_temp, tipo_declaracao, tipos_selecionados=None):
    """Processa e baixa documentos PER/DCOMP (Verificação e Log por Página)."""
    from selenium.webdriver.support.ui import Select
    import re

    log("\n── Iniciando PER/DCOMP (Download Direto e Varredura) ──")
    aba_original = driver.current_window_handle

    driver.switch_to.default_content()
    try:
        iframe = WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.ID, "frmApp"))
        )
        driver.switch_to.frame(iframe)
        log("    [✔] Dentro do Iframe frmApp.")
    except:
        log("    [!] Iframe não encontrado, tentando na raiz.")

    if tipos_selecionados is None:
        tipos_selecionados = []

    tipos_alvo = [
        "Declaração de Compensação",
        "Pedido de Restituição",
        "Pedido de Ressarcimento",
        "Pedido de Reembolso",
    ]

    if tipos_selecionados:
        tipos_alvo = [t for t in tipos_alvo if t in tipos_selecionados]

    if not tipos_alvo:
        log("    [!] Nenhum tipo de arquivo foi selecionado. Abortando.")
        return 0, set()

    total_geral = 0

    for tipo in tipos_alvo:
        verificar_parada()
        log(f"\n[Filtro] Verificando: {tipo.upper()}")

        try:
            driver.switch_to.window(aba_original)
            driver.switch_to.frame("frmApp")
        except Exception:
            pass

        from __main__ import obter_pasta_documentos, pasta_cliente
        pasta_final_tipo = os.path.join(obter_pasta_documentos(pasta_cliente, criar=False), "PER-DCOMP", tipo.upper())
        os.makedirs(pasta_final_tipo, exist_ok=True)

        caminho_abs_tipo = os.path.abspath(pasta_final_tipo)
        driver.execute_cdp_cmd(
            "Browser.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": caminho_abs_tipo,
                "eventsEnabled": True,
            },
        )
        log(f"    [📁] Destino fixado em: {os.path.basename(pasta_final_tipo)}")

        try:
            sel_xpath = "//select[contains(@id, 'tipoDocumento')] | //*[contains(text(), 'Tipo de Documento')]/following::select[1]"
            select_el = WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.XPATH, sel_xpath))
            )

            botoes_antes = driver.find_elements(
                By.CSS_SELECTOR, "i.icon-print, i.pi-print, .fa-print"
            )

            Select(select_el).select_by_visible_text(tipo)

            driver.execute_script(
                "arguments[0].dispatchEvent(new Event('change', {bubbles: true}));",
                select_el,
            )

            try:
                WebDriverWait(driver, 20).until(
                    lambda d: len(
                        d.find_elements(
                            By.CSS_SELECTOR, "i.icon-print, i.pi-print, .fa-print"
                        )
                    )
                    != len(botoes_antes)
                )
            except:
                time.sleep(7)

            try:
                btn_primeira = driver.find_elements(
                    By.XPATH, "//span[contains(text(), '«')] | //a[contains(., '«')]"
                )
                if btn_primeira and btn_primeira[0].is_displayed():
                    driver.execute_script("arguments[0].click();", btn_primeira[0])
                    time.sleep(4)
            except:
                pass

            pagina_atual = 1

            while True:
                verificar_parada()

                while True:
                    verificar_parada()
                    try:
                        loading_elements = driver.find_elements(
                            By.XPATH,
                            "//*[contains(@class, 'loading')] | //*[contains(text(), 'Processando')]",
                        )
                        if not loading_elements or not any(
                            el.is_displayed() for el in loading_elements
                        ):
                            break
                    except Exception:
                        break
                    time.sleep(1.5)

                WebDriverWait(driver, 10).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )

                botoes = driver.find_elements(
                    By.CSS_SELECTOR, "i.icon-print, i.pi-print, .fa-print"
                )

                if not botoes:
                    log(f"    ➜ Nenhum documento visível na página {pagina_atual}.")
                    break

                log(f"    [Página {pagina_atual}] Clicando em {len(botoes)} documentos...")

                abas_antes = set(driver.window_handles)
                
                # FOTO 1: Arquivos existentes ANTES dos cliques desta página
                arquivos_antes = set(os.listdir(pasta_final_tipo))

                # Dispara os cliques
                for i in range(len(botoes)):
                    verificar_parada()
                    try:
                        botoes_refresh = driver.find_elements(
                            By.CSS_SELECTOR, "i.icon-print, i.pi-print, .fa-print"
                        )
                        if i >= len(botoes_refresh):
                            break

                        btn_imprimir = botoes_refresh[i].find_element(
                            By.XPATH, "./ancestor::span | ./ancestor::button"
                        )

                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn_imprimir)
                        time.sleep(0.1)

                        driver.execute_script("arguments[0].click();", btn_imprimir)
                        time.sleep(0.8)
                    except Exception as e:
                        log(f"    [ERRO] Falha ao clicar no item {i+1}: {str(e)[:80]}")

                # Tratamento de Abas Novas
                abas_depois = set(driver.window_handles)
                novas_abas = list(abas_depois - abas_antes)

                if novas_abas:
                    for idx, aba in enumerate(novas_abas):
                        verificar_parada()
                        try:
                            driver.switch_to.window(aba)
                            WebDriverWait(driver, 10).until(
                                lambda d: d.execute_script("return document.readyState") == "complete"
                            )
                            time.sleep(1.0)
                            pdf_data = driver.execute_cdp_cmd("Page.printToPDF", {"printBackground": True})
                            nome_arq = f"PERDCOMP_PAG{pagina_atual}_{idx}.pdf"
                            caminho_salvar = os.path.join(pasta_final_tipo, nome_arq)

                            with open(caminho_salvar, "wb") as f:
                                f.write(base64.b64decode(pdf_data["data"]))
                        except Exception:
                            pass
                        finally:
                            try:
                                driver.close()
                            except:
                                pass

                try:
                    driver.switch_to.window(aba_original)
                    driver.switch_to.frame("frmApp")
                except:
                    pass

                # MONITORAMENTO: Aguarda conclusão dos downloads
                tempo_espera = 0
                while tempo_espera < 90:
                    verificar_parada()

                    residuos_temp = [f for f in os.listdir(pasta_temp) if not f.endswith((".crdownload", ".tmp"))]
                    for residuo in residuos_temp:
                        try:
                            shutil.move(os.path.join(pasta_temp, residuo), os.path.join(pasta_final_tipo, residuo))
                        except:
                            pass

                    incompletos_final = [f for f in os.listdir(pasta_final_tipo) if f.endswith((".crdownload", ".tmp"))]
                    incompletos_temp = [f for f in os.listdir(pasta_temp) if f.endswith((".crdownload", ".tmp"))]
                    
                    if not incompletos_final and not incompletos_temp:
                        time.sleep(2.0)  # Margem de estabilização
                        break
                        
                    time.sleep(1.5)
                    tempo_espera += 1.5

                # FOTO 2: Compara e revela arquivos novos da página
                arquivos_depois = set(os.listdir(pasta_final_tipo))
                arquivos_novos_brutos = arquivos_depois - arquivos_antes
                
                arquivos_novos = [f for f in arquivos_novos_brutos if not f.endswith((".crdownload", ".tmp"))]

                if arquivos_novos:
                    for nome_arq in arquivos_novos:
                        if nome_arq.startswith("PERDCOMP_"):
                            nome_limpo = nome_arq 
                        else:
                            match_dup = re.search(r"^(.*?)\s*\(\d+\)(\.[a-zA-Z0-9]+)$", nome_arq)
                            if match_dup:
                                nome_limpo = (match_dup.group(1) + match_dup.group(2)).upper()
                            else:
                                nome_limpo = nome_arq.upper()

                        origem = os.path.join(pasta_final_tipo, nome_arq)
                        destino = os.path.join(pasta_final_tipo, nome_limpo)

                        if os.path.abspath(origem) != os.path.abspath(destino):
                            try:
                                substituir_arquivo(origem, destino)
                                log(f"    [✔] Salvo: {nome_limpo}")
                            except:
                                log(f"    [✔] Salvo: {nome_arq}")
                        else:
                            try:
                                os.replace(origem, destino)
                            except:
                                pass
                            log(f"    [✔] Salvo: {nome_limpo}")
                            
                    total_geral += len(arquivos_novos)
                else:
                    log("    [!] Nenhum arquivo novo contabilizado nesta página.")


                # --- AVANÇAR PÁGINA ---
                try:
                    btn_proximo = driver.find_elements(
                        By.XPATH,
                        "//span[contains(@class, 'ui-paginator-next')] | //a[@aria-label='Próximo'] | //a[span[text()='»']] | //*[contains(@title, 'Próxima')]",
                    )

                    clicou_proximo = False

                    for btn in btn_proximo:
                        if btn.is_displayed():
                            classe_btn = btn.get_attribute("class") or ""
                            pai_disabled = False
                            try:
                                pai = btn.find_element(By.XPATH, "./parent::li")
                                if "disabled" in (pai.get_attribute("class") or "").lower():
                                    pai_disabled = True
                            except:
                                pass

                            if "disabled" in classe_btn.lower() or "inativo" in classe_btn.lower() or pai_disabled:
                                continue

                            botoes_print_atuais = driver.find_elements(
                                By.CSS_SELECTOR, "i.icon-print, i.pi-print, .fa-print"
                            )
                            elem_antigo = botoes_print_atuais[0] if botoes_print_atuais else None

                            driver.execute_script("arguments[0].click();", btn)
                            clicou_proximo = True
                            log("    [➔] Avançando para próxima página...")
                            pagina_atual += 1

                            if elem_antigo:
                                try:
                                    WebDriverWait(driver, 10).until(EC.staleness_of(elem_antigo))
                                except:
                                    pass

                            while True:
                                verificar_parada()
                                try:
                                    loading_elements = driver.find_elements(
                                        By.XPATH,
                                        "//*[contains(@class, 'loading')] | //*[contains(text(), 'Processando')]",
                                    )
                                    if not loading_elements or not any(el.is_displayed() for el in loading_elements):
                                        break
                                except Exception:
                                    break
                                time.sleep(1.5)
                            break

                    if not clicou_proximo:
                        break

                except Exception as e:
                    log(f"    [ERRO] Erro ao tentar avançar de página: {e}")
                    break

        except Exception as e:
            log(f"    [❌] Erro crítico no tipo {tipo}: {str(e)}")

    return total_geral, set()


# ─────────────────────────────────────────────────────────────────
# MÓDULO 4: PGDAS
# ─────────────────────────────────────────────────────────────────
PGDAS_XPATH_ANO = "//input[contains(@placeholder, '20') or contains(@name, 'ano') or @id='ano']"
PGDAS_XPATH_CONSULTAR = "//button[@type='submit' and contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'consultar')]"


def _buscar_contexto_pgdas(driver, localizar, abas=None):
    """Procura um controle nas guias permitidas e mantém seu contexto de frame."""
    verificar_parada()

    def procurar(nivel=0):
        resultado = localizar()
        if resultado:
            return resultado
        if nivel >= 4:
            return False
        for frame in driver.find_elements(By.CSS_SELECTOR, "iframe, frame"):
            entrou = False
            encontrou = False
            try:
                driver.switch_to.frame(frame)
                entrou = True
                resultado = procurar(nivel + 1)
                if resultado:
                    encontrou = True
                    return resultado
            except (StaleElementReferenceException, NoSuchFrameException):
                pass
            finally:
                if entrou and not encontrou:
                    driver.switch_to.parent_frame()
        return False

    for aba in abas if abas is not None else [driver.current_window_handle]:
        try:
            driver.switch_to.window(aba)
            driver.switch_to.default_content()
            resultado = procurar()
            if resultado:
                return resultado
        except (StaleElementReferenceException, NoSuchFrameException, NoSuchWindowException):
            continue
    return False


def localizar_tela_pgdas(driver, timeout=12, abas=None):
    """Confirma os controles de consulta, sem reutilizar outras guias antigas."""
    def controles():
        anos = driver.find_elements(By.XPATH, PGDAS_XPATH_ANO)
        botoes = driver.find_elements(By.XPATH, PGDAS_XPATH_CONSULTAR)
        return (
            any(el.is_displayed() and el.is_enabled() for el in anos)
            and any(el.is_displayed() and el.is_enabled() for el in botoes)
        )

    try:
        WebDriverWait(driver, timeout, poll_frequency=0.2).until(
            lambda d: _buscar_contexto_pgdas(d, controles, abas)
        )
        return True
    except TimeoutException:
        return False


def navegar_para_pgdas(driver):
    """Abre Simples Nacional > PGDAS-D > Declaração Mensal > Consultar Declarações."""
    aba_ecac = focar_aba_principal_ecac(driver)
    if not aba_ecac:
        raise RuntimeError("Guia principal do e-CAC não encontrada para abrir o PGDAS.")
    driver.switch_to.default_content()
    abas_antes = set(driver.window_handles)

    def abas_permitidas():
        # Uma guia antiga de outro cliente não pode satisfazer esta navegação.
        novas = [aba for aba in driver.window_handles if aba not in abas_antes]
        return novas + [aba_ecac]

    def localizar_clicavel(xpath):
        return next((el for el in driver.find_elements(By.XPATH, xpath)
                     if el.is_displayed() and el.is_enabled()), False)

    def clicar(elemento):
        try:
            elemento.click()
        except ElementClickInterceptedException:
            driver.execute_script("arguments[0].click();", elemento)

    def clicar_etapa(xpath, descricao, expandir=False):
        log(f"PGDAS: {descricao}...")

        def executar(d):
            elemento = _buscar_contexto_pgdas(
                d, lambda: localizar_clicavel(xpath), abas_permitidas()
            )
            if not elemento:
                return False
            if expandir:
                if elemento.get_attribute("aria-expanded") == "true":
                    return True
                # O painel já tem onclick: clicar nele evita acionar também
                # o data-toggle do link e expandir/fechar o menu duas vezes.
                elemento = elemento.find_element(
                    By.XPATH, "./ancestor::div[contains(@class, 'panel-heading')][1]"
                )
            clicar(elemento)
            return True

        try:
            WebDriverWait(
                driver, 60, poll_frequency=0.2,
                ignored_exceptions=(StaleElementReferenceException,),
            ).until(executar)
        except TimeoutException as erro:
            raise RuntimeError(f"PGDAS: não foi possível concluir a etapa '{descricao}'.") from erro

    clicar_etapa("//a[normalize-space(.)='Simples Nacional']", "abrindo Simples Nacional")
    clicar_etapa("//a[contains(@href, 'Aplicacao.aspx?id=10009')]", "abrindo PGDAS-D e Defis 2018")
    clicar_etapa(
        "//a[@href='#collapseOne' and contains(normalize-space(.), 'Declaração Mensal')]",
        "expandindo Declaração Mensal", expandir=True,
    )
    clicar_etapa(
        "//a[contains(@href, '/pgdasd2018.app/Consulta') and normalize-space(.)='Consultar Declarações']",
        "abrindo Consultar Declarações",
    )
    log("PGDAS: aguardando os controles de consulta ficarem disponíveis...")
    if not localizar_tela_pgdas(driver, timeout=60, abas=abas_permitidas()):
        raise RuntimeError("PGDAS: campo de ano e botão Consultar não ficaram disponíveis; captação bloqueada.")
    log("✔ Tela de consulta do PGDAS pronta para captação.")
    return True


def processar_pgdas(driver, pasta_temp, tipo_declaracao="PGDAS"):
    log("\n── Iniciando PGDAS ──")
    ano_fim = datetime.date.today().year
    arquivos_baixados = 0
    meses_sucesso = set()

    pasta_pgdas = os.path.join(obter_pasta_documentos(pasta_cliente), SUBPASTA_PGDAS)
    os.makedirs(pasta_pgdas, exist_ok=True)
    driver.execute_cdp_cmd(
        "Browser.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": os.path.abspath(pasta_temp), "eventsEnabled": True},
    )

    if not localizar_tela_pgdas(driver):
        raise RuntimeError("Tela de consulta do PGDAS não localizada após a navegação automática.")

    for ano_busca in range(ANO_INICIO, ano_fim + 1):
        verificar_parada()
        log(f"\n[PGDAS] Consultando Ano-calendário: {ano_busca}...")
        aba_original = driver.current_window_handle
        if not localizar_tela_pgdas(driver, timeout=30, abas=[aba_original]):
            raise RuntimeError(f"PGDAS: controles da consulta indisponíveis para o ano {ano_busca}.")
        el_in = next(el for el in driver.find_elements(By.XPATH, PGDAS_XPATH_ANO)
                     if el.is_displayed() and el.is_enabled())
        el_bt = next(el for el in driver.find_elements(By.XPATH, PGDAS_XPATH_CONSULTAR)
                     if el.is_displayed() and el.is_enabled())
        el_in.clear()
        el_in.send_keys(str(ano_busca))
        time.sleep(0.8)
        driver.execute_script("arguments[0].click();", el_bt)
        time.sleep(3.5)

        limite_espera = time.time() + 15
        tabela_carregada = False
        while time.time() < limite_espera:
            verificar_parada()
            if driver.find_elements(
                By.XPATH, "//*[contains(text(), 'Não existem declarações transmitidas')]"
            ):
                tabela_carregada = "vazio"
                break
            if driver.find_elements(By.XPATH, "//th[@class='pa' or contains(text(), 'PA ')]"):
                tabela_carregada = "ok"
                break
            time.sleep(1.5)

        if tabela_carregada != "ok":
            continue

        pasta_ano = os.path.join(pasta_pgdas, str(ano_busca))
        os.makedirs(pasta_ano, exist_ok=True)
        xpath_botoes_decl = "//a[@data-content='Imprimir Declaração']"
        pagina_atual = 1

        while True:
            verificar_parada()
            botoes_imprimir = driver.find_elements(By.XPATH, xpath_botoes_decl)
            if not botoes_imprimir:
                break

            mapa_pa_ultimo_indice = {}
            for i in range(len(botoes_imprimir)):
                try:
                    th_pa = botoes_imprimir[i].find_element(
                        By.XPATH, "./preceding::th[@class='pa'][1]"
                    )
                    texto_pa = th_pa.text.strip().replace("/", "-").replace(" ", "_")
                except Exception:
                    texto_pa = f"PA_Desconhecido_{i}"
                mapa_pa_ultimo_indice[texto_pa] = i

            for idx in sorted(mapa_pa_ultimo_indice.values()):
                verificar_parada()
                try:
                    botoes_refresh = driver.find_elements(By.XPATH, xpath_botoes_decl)
                    if idx >= len(botoes_refresh):
                        break
                    btn = botoes_refresh[idx]
                    try:
                        texto_pa = (
                            btn.find_element(By.XPATH, "./preceding::th[@class='pa'][1]")
                            .text.strip()
                            .replace("/", "-")
                            .replace(" ", "_")
                        )
                    except Exception:
                        texto_pa = f"Declaracao_{idx+1:02d}"

                    sufixo_pagina = f" - {pagina_atual}" if pagina_atual > 1 else ""
                    nome_arquivo = f"{texto_pa}{sufixo_pagina}.pdf"
                    caminho_final = os.path.join(pasta_ano, nome_arquivo)

                    for f in os.listdir(pasta_temp):
                        try:
                            os.remove(os.path.join(pasta_temp, f))
                        except Exception:
                            pass

                    abas_antes = set(driver.window_handles)
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});", btn
                    )
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", btn)

                    sucesso_download = False
                    abriu_aba = False
                    for _ in range(30):
                        if len(driver.window_handles) > len(abas_antes):
                            abriu_aba = True
                            sucesso_download = True
                            break
                        arquivos = [
                            f
                            for f in os.listdir(pasta_temp)
                            if not f.endswith(EXT_DOWNLOAD_INCOMPLETO)
                        ]
                        if arquivos:
                            sucesso_download = True
                            break
                        time.sleep(0.5)

                    if sucesso_download:
                        if abriu_aba:
                            nova_aba = (set(driver.window_handles) - abas_antes).pop()
                            driver.switch_to.window(nova_aba)
                            time.sleep(1.5)
                            pdf_dict = driver.execute_cdp_cmd(
                                "Page.printToPDF", {"printBackground": True}
                            )
                            gravar_pdf_substituindo(
                                caminho_final, base64.b64decode(pdf_dict["data"])
                            )
                            driver.close()
                            driver.switch_to.window(aba_original)
                            if not localizar_tela_pgdas(driver, timeout=30, abas=[aba_original]):
                                raise RuntimeError("PGDAS: não foi possível retornar à consulta após salvar o PDF.")
                        else:
                            arquivos = [
                                f
                                for f in os.listdir(pasta_temp)
                                if not f.endswith(EXT_DOWNLOAD_INCOMPLETO)
                            ]
                            if arquivos:
                                substituir_arquivo(
                                    os.path.join(pasta_temp, arquivos[0]), caminho_final
                                )
                        arquivos_baixados += 1
                        log(f"    [✔] Salvo: {nome_arquivo}")
                except Exception:
                    pass

            try:
                btn_next = driver.find_element(By.ID, "btn-next-page")
                is_disabled = btn_next.get_attribute("disabled")
                classe_btn = btn_next.get_attribute("class") or ""
                if (
                    btn_next.is_displayed()
                    and not is_disabled
                    and "disabled" not in classe_btn
                ):
                    tabela_antiga = driver.find_element(By.XPATH, "//table//tbody")
                    driver.execute_script("arguments[0].click();", btn_next)
                    try:
                        WebDriverWait(driver, 10).until(EC.staleness_of(tabela_antiga))
                    except Exception:
                        pass
                    time.sleep(2)
                    pagina_atual += 1
                else:
                    break
            except Exception:
                break

    registrar_pgdas_no_relatorio(pasta_cliente)
    return arquivos_baixados, meses_sucesso


# ─────────────────────────────────────────────────────────────────
# MÓDULO 5: DARF
# ─────────────────────────────────────────────────────────────────
def limpar_darfs_obsoletos(pasta_darf, codigo, nomes_atuais):
    prefixo = f"{codigo} - ".lower()
    manter = {n.lower() for n in nomes_atuais}
    removidos = []
    for nome in os.listdir(pasta_darf):
        nome_l = nome.lower()
        if nome_l.startswith(prefixo) and nome_l.endswith(".pdf") and nome_l not in manter:
            try:
                os.remove(os.path.join(pasta_darf, nome))
                removidos.append(nome)
            except Exception:
                pass
    return removidos


def processar_darf(driver, pasta_temp, tipo_declaracao="DARF"):
    log("\n── Iniciando Módulo: Pesquisa de DARFs ──")
    wait = WebDriverWait(driver, 40)
    arquivos_baixados = 0
    meses_sucesso = set()

    driver.execute_cdp_cmd(
        "Browser.setDownloadBehavior",
        {"behavior": "allow", "downloadPath": os.path.abspath(pasta_temp), "eventsEnabled": True},
    )

    try:
        for aba in driver.window_handles:
            driver.switch_to.window(aba)
            if driver.find_elements(By.XPATH, "//span[text()='Tipo de documento']"):
                break
    except Exception:
        pass

    aba_principal = driver.current_window_handle
    pasta_darf = os.path.join(obter_pasta_documentos(pasta_cliente), SUBPASTA_DARF)
    os.makedirs(pasta_darf, exist_ok=True)

    try:
        xpath_tipo_doc = "//span[text()='Tipo de documento']/ancestor::br-label/following-sibling::ng-select//input"
        input_tipo_doc = wait.until(EC.element_to_be_clickable((By.XPATH, xpath_tipo_doc)))
        input_tipo_doc.send_keys("DARF")
        pausa(0.5, 1.0)
        input_tipo_doc.send_keys(Keys.ENTER)

        input_data_ini = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@name='ini']")))
        input_data_ini.send_keys(Keys.CONTROL + "a", Keys.DELETE, f"01/01/{ANO_INICIO}", Keys.TAB)

        btn_filtro_avancado = wait.until(
            EC.element_to_be_clickable((By.XPATH, "//button[@data-bs-target='#ftlAvancado']"))
        )
        btn_filtro_avancado.click()
        pausa(1.0, 1.5)

        xpath_caixa_select = "//span[text()='Código de receita']/ancestor::br-label/following-sibling::ng-select"
        xpath_input_receita = f"{xpath_caixa_select}//input"

        for codigo in CODIGOS_RECEITA:
            verificar_parada()
            for tentativa in range(1, 3):
                try:
                    driver.switch_to.window(aba_principal)
                    log(f"   Processando código: {codigo} (Tentativa {tentativa}/2)")
                    caixa_select = wait.until(
                        EC.element_to_be_clickable((By.XPATH, xpath_caixa_select))
                    )
                    caixa_select.click()
                    pausa(0.4, 0.7)

                    input_codigo = wait.until(
                        EC.element_to_be_clickable((By.XPATH, xpath_input_receita))
                    )
                    input_codigo.send_keys(Keys.CONTROL + "a", Keys.DELETE, codigo)
                    pausa(0.5, 0.8)
                    input_codigo.send_keys(Keys.ENTER)

                    btn_filtrar = wait.until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "//button[@type='submit' and contains(., 'Filtrar')]")
                        )
                    )
                    driver.execute_script("arguments[0].click();", btn_filtrar)
                    pausa(1.8, 2.5)

                    elemento_resultado = wait.until(
                        EC.presence_of_element_located(
                            (By.XPATH, "//datatable-body-row | //div[contains(@class, 'empty-content')]")
                        )
                    )
                    if "empty-content" in (elemento_resultado.get_attribute("class") or ""):
                        log(f"   Nenhum documento para o código {codigo}.")
                        break

                    try:
                        combo_exibir = driver.find_element(
                            By.XPATH, "//label[contains(text(), 'Exibir')]/following-sibling::br-select//ng-select"
                        )
                        combo_exibir.click()
                        pausa(0.4, 0.8)
                        wait.until(
                            EC.element_to_be_clickable(
                                (By.XPATH, "//div[contains(@class, 'ng-option')]//span[text()='100']")
                            )
                        ).click()
                        pausa(2.0, 3.0)
                    except Exception:
                        pass

                    pagina_atual = 1
                    arquivos_do_codigo = set()
                    while True:
                        verificar_parada()
                        check_todos = wait.until(
                            EC.presence_of_element_located(
                                (By.XPATH, "//input[@aria-label='Select all rows'] | //datatable-header//input[@type='checkbox']")
                            )
                        )
                        driver.execute_script("arguments[0].click();", check_todos)
                        pausa(1.0, 1.5)

                        btn_relatorio = wait.until(
                            EC.element_to_be_clickable(
                                (By.XPATH, "//button[contains(translate(., 'RELATÓRIO SELECIONADOS', 'relatório selecionados'), 'relatório selecionados')] | //button[contains(., 'Relatório Selecionados')]")
                            )
                        )
                        arquivos_antes_temp = set(os.listdir(pasta_temp))
                        driver.execute_script("arguments[0].click();", btn_relatorio)

                        inicio_espera = time.time()
                        arquivo_novo_temp = None
                        while time.time() - inicio_espera < 90:
                            verificar_parada()
                            novos_temp = set(os.listdir(pasta_temp)) - arquivos_antes_temp
                            if novos_temp:
                                cand = list(novos_temp)[0]
                                if not cand.endswith(EXT_DOWNLOAD_INCOMPLETO):
                                    arquivo_novo_temp = os.path.join(pasta_temp, cand)
                                    break
                            time.sleep(1.2)

                        denominacao = DICIONARIO_CODIGOS.get(codigo, "DARF")
                        nome_limpo = re.sub(r'[\\/*?:"<>|]', "", denominacao)
                        sufixo_pag = f" {pagina_atual}" if pagina_atual > 1 else ""
                        novo_nome_arquivo = f"{codigo} - {nome_limpo}{sufixo_pag}.pdf"
                        novo_caminho = os.path.join(pasta_darf, novo_nome_arquivo)
                        arquivos_do_codigo.add(novo_nome_arquivo)

                        if arquivo_novo_temp:
                            substituir_arquivo(arquivo_novo_temp, novo_caminho)
                            log(f"   [✔] Arquivo salvo: {novo_nome_arquivo}")
                            arquivos_baixados += 1
                        else:
                            break

                        try:
                            btn_next = driver.find_element(By.ID, "btn-next-page")
                            if (
                                btn_next.is_displayed()
                                and not btn_next.get_attribute("disabled")
                                and "disabled" not in (btn_next.get_attribute("class") or "")
                            ):
                                driver.execute_script("arguments[0].click();", btn_next)
                                time.sleep(2.5)
                                pagina_atual += 1
                            else:
                                break
                        except Exception:
                            break

                    if arquivos_do_codigo:
                        limpar_darfs_obsoletos(pasta_darf, codigo, arquivos_do_codigo)
                    break
                except Exception as e:
                    if "interrompida" in str(e).lower():
                        raise e
                    time.sleep(1.5)

        log("Varredura de Códigos de Receita concluída!")
    except Exception as e:
        if "interrompida" in str(e).lower():
            raise e
        log(f"ERRO no Módulo DARF: {str(e)}")

    return arquivos_baixados, meses_sucesso


# ─────────────────────────────────────────────────────────────────
# Relatório local do cliente
TIPOS = {
    "EFD-ICMS/IPI": ("EFD-ICMS IPI", 3, "mensal"),
    "EFD-Contribuições": ("EFD-Contribuicoes", 5, "mensal"),
    "ECF": ("ECF", 9, "anual"),
    "ECD": ("ECD", 2, "anual"),
}


def criar_pastas_speds(pasta_cliente):
    raiz = Path(pasta_cliente) / "SPEDS"
    for subpasta, _, _ in TIPOS.values():
        (raiz / subpasta).mkdir(parents=True, exist_ok=True)
    return raiz


def _periodo_arquivo(caminho, indice, periodicidade):
    with caminho.open("r", encoding="latin-1") as arquivo:
        for linha in arquivo:
            campos = linha.strip().split("|")
            if "0000" not in campos:
                continue
            posicao = campos.index("0000") + indice
            if posicao >= len(campos):
                raise ValueError("registro 0000 sem data na posição esperada")
            valor = "".join(c for c in campos[posicao] if c.isdigit())
            data = dt.datetime.strptime(valor[:8], "%d%m%Y").date()
            return data.year if periodicidade == "anual" else (data.year, data.month)
    raise ValueError("registro 0000 não encontrado")


def _esperados(inicio, periodicidade, hoje):
    if inicio is None or inicio == dt.date.max:
        return set()
    if periodicidade == "anual":
        return set(range(inicio.year, hoje.year))
    ultimo = (hoje.year * 12 + hoje.month) - 2
    primeiro = inicio.year * 12 + inicio.month
    return {(n // 12, n % 12 + 1) for n in range(primeiro - 1, ultimo)}


def verificar_speds(pasta_cliente, inicio=None, hoje=None):
    """Devolve contagens e períodos faltantes, sem alterar arquivos SPED."""
    hoje = hoje or dt.date.today()
    raiz = Path(pasta_cliente) / "SPEDS"
    resultado = {}
    for tipo, (subpasta, indice, periodicidade) in TIPOS.items():
        pasta = raiz / subpasta
        arquivos = sorted(pasta.glob("*.txt")) if pasta.is_dir() else []
        encontrados, erros, detalhes = set(), [], []
        for caminho in arquivos:
            try:
                periodo = _periodo_arquivo(caminho, indice, periodicidade)
                encontrados.add(periodo)
                rotulo = str(periodo) if periodicidade == "anual" else f"{periodo[1]:02d}/{periodo[0]}"
                detalhes.append(f"{caminho.name} — {rotulo}")
            except (OSError, ValueError) as erro:
                erros.append(f"{caminho.name}: {erro}")
        esperados = _esperados(inicio, periodicidade, hoje)
        resultado[tipo] = {
            "pasta_existe": pasta.is_dir(),
            "arquivos": len(arquivos),
            "periodos": sorted(encontrados),
            "arquivos_lidos": detalhes,
            "faltantes": sorted(esperados - encontrados),
            "erros": erros,
        }
    return resultado


def formatar_verificacao(resultado, inicio):
    linhas = ["Conferência pelo registro 0000 dos arquivos .txt em SPEDS/<tipo>."]
    if inicio is None:
        linhas.append("Períodos faltantes: consulte o CNPJ primeiro para definir a data inicial.")
    elif inicio == dt.date.max:
        linhas.append("Empresa optante pelo Simples Nacional: períodos esperados não aplicados.")
    else:
        linhas.append(f"Início da contagem: {inicio:%m/%Y}.")
    for tipo, dados in resultado.items():
        linhas.extend(("", tipo, f"Arquivos TXT: {dados['arquivos']}",
                       f"Períodos encontrados: {len(dados['periodos'])}"))
        linhas.extend(f"- {arquivo}" for arquivo in dados["arquivos_lidos"])
        if not dados["pasta_existe"]:
            linhas.append("Pasta não encontrada.")
        if inicio is not None and inicio != dt.date.max:
            faltantes = [str(p) if isinstance(p, int) else f"{p[1]:02d}/{p[0]}"
                         for p in dados["faltantes"]]
            linhas.append("Faltantes: " + (", ".join(faltantes) if faltantes else "nenhum"))
        linhas.extend(f"Erro de leitura: {erro}" for erro in dados["erros"])
    return "\n".join(linhas)


NOME_RELATORIO = "RELATORIO_DOCUMENTOS.txt"


def atualizar_relatorio(pasta_do_cliente, secao=None, conteudo=None):
    """Atualiza uma seção e refaz o inventário dos arquivos do cliente."""
    os.makedirs(pasta_do_cliente, exist_ok=True)
    caminho = os.path.join(pasta_do_cliente, NOME_RELATORIO)
    secoes = {}
    if os.path.isfile(caminho):
        texto = open(caminho, encoding="utf-8").read()
        for bloco in re.split(r"(?=^## )", texto, flags=re.MULTILINE):
            if bloco.startswith("## "):
                titulo, _, corpo = bloco.partition("\n")
                secoes[titulo[3:].strip()] = corpo.strip()
    if secao is not None:
        secoes[secao] = str(conteudo or "Sem observações.").strip()

    arquivos = []
    for raiz, pastas, nomes in os.walk(pasta_do_cliente):
        pastas[:] = sorted(p for p in pastas if p not in {"__pycache__", ".git"})
        for nome in sorted(nomes):
            if nome == NOME_RELATORIO or nome.startswith("~$") or nome.lower().endswith(EXT_DOWNLOAD_INCOMPLETO):
                continue
            completo = os.path.join(raiz, nome)
            relativo = os.path.relpath(completo, pasta_do_cliente)
            arquivos.append(f"- {relativo} ({os.path.getsize(completo):,} bytes)")
    secoes["Arquivos na pasta"] = "\n".join(arquivos) if arquivos else "Nenhum arquivo encontrado."
    ordem = ["Dados do cliente", "Captação DCTF Normal", "Captação DCTF-Web",
             "Captação PER/DCOMP", "Captação PGDAS", "Captação DARF",
             "Verificação de SPEDs", "Conferência SPED", "Arquivos na pasta"]
    titulos = [t for t in ordem if t in secoes] + sorted(t for t in secoes if t not in ordem)
    texto = ("RELATÓRIO DE DOCUMENTOS DO CLIENTE\n" + "=" * 40 + "\n"
             + f"Cliente: {os.path.basename(pasta_do_cliente)}\n"
             + f"Atualizado em: {datetime.datetime.now():%d/%m/%Y %H:%M:%S}\n\n")
    texto += "\n\n".join(f"## {titulo}\n{secoes[titulo]}" for titulo in titulos) + "\n"
    temporario = caminho + ".tmp"
    with open(temporario, "w", encoding="utf-8") as arquivo:
        arquivo.write(texto)
    os.replace(temporario, caminho)
    return caminho


def normalizar_nome(texto):
    texto = str(texto)
    texto = re.sub(r"\.xlsx?$", "", texto, flags=re.IGNORECASE)
    texto = re.sub(r"\.xls$", "", texto, flags=re.IGNORECASE)
    texto = (
        unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("utf-8")
    )
    return re.sub(r"[^a-z0-9]", "", texto.lower())




def consultar_cnpj_api(cnpj):
    """Consulta os dados públicos do CNPJ informado."""
    cnpj_limpo = normalizar_cnpj(cnpj)
    if not cnpj_limpo:
        raise ValueError(f"CNPJ inválido para consulta: {cnpj}")
    status("Consultando CNPJ automaticamente...", "orange")
    resposta = requests.get(f"https://open.cnpja.com/office/{cnpj_limpo}", timeout=20)
    resposta.raise_for_status()
    dados = resposta.json()
    if not isinstance(dados, dict):
        raise ValueError("A consulta do CNPJ retornou dados inválidos.")
    return dados


def atualizar_dados_cnpj_cliente(cnpj, pasta_alvo, dados):
    """Atualiza os dados do cliente atual no relatório antes da captação."""
    global data_abertura_atual, data_fim_simples_global
    data_abertura_atual = "Não informada"
    data_fim_simples_global = None
    founded_raw = dados.get("founded", "")
    if not founded_raw and "offices" in dados and len(dados["offices"]) > 0:
        founded_raw = dados["offices"][0].get("founded", "")

    if founded_raw:
        ano, mes, dia = founded_raw.split("-")
        data_abertura_atual = f"{dia}/{mes}/{ano}"
    else:
        data_abertura_atual = "Não informada"

    simples = dados.get("company", {}).get("simples") or dados.get(
        "simples", {}
    )
    optante_simples = simples.get("optant", False)
    historico = simples.get("history", [])

    data_fim_simples_global = None
    ultimo_periodo = None
    if historico:
        hist_valido = [
            h for h in historico if h.get("from") and h.get("until")
        ]
        if hist_valido:
            ultimo_periodo = sorted(
                hist_valido, key=lambda x: x.get("until")
            )[-1]

    if optante_simples:
        data_fim_simples_global = datetime.date.max
    elif ultimo_periodo:
        ano_f, mes_f, dia_f = map(int, ultimo_periodo.get("until").split("-"))
        data_fim_simples_global = datetime.date(ano_f, mes_f, dia_f)

    if optante_simples:
        data_inicio_raw = simples.get("since")
        if data_inicio_raw:
            ano_i, mes_i, dia_i = data_inicio_raw.split("-")
            texto_simples = f"{dia_i}/{mes_i}/{ano_i} - até o momento"
        else:
            texto_simples = "Sim - até o momento"
        if ultimo_periodo:
            ano_e, mes_e, dia_e = ultimo_periodo.get("until").split("-")
            texto_simples += (
                f" (Exclusão anterior em {dia_e}/{mes_e}/{ano_e})"
            )
    else:
        if ultimo_periodo:
            ano_i, mes_i, dia_i = ultimo_periodo.get("from").split("-")
            ano_f, mes_f, dia_f = ultimo_periodo.get("until").split("-")
            texto_simples = (
                f"{dia_i}/{mes_i}/{ano_i} - {dia_f}/{mes_f}/{ano_f}"
            )
        else:
            data_inicio_raw = simples.get("since")
            if data_inicio_raw:
                ano_i, mes_i, dia_i = data_inicio_raw.split("-")
                texto_simples = f"{dia_i}/{mes_i}/{ano_i} - Excluída"
            else:
                texto_simples = "Não optante / Sem dados"
    atualizar_relatorio(
        pasta_alvo, "Dados do cliente",
        f"CNPJ: {cnpj}\nAbertura: {data_abertura_atual}\nSimples Nacional: {texto_simples}",
    )
    log(f"Consulta automática {cnpj}: abertura {data_abertura_atual} | Simples: {texto_simples}")
    return True


def inicio_contagem_speds(pasta_do_cliente):
    """Recupera a data de referência da consulta feita para este cliente."""
    caminho = os.path.join(pasta_do_cliente, NOME_RELATORIO)
    if not os.path.isfile(caminho):
        return None
    with open(caminho, encoding="utf-8") as arquivo:
        dados = arquivo.read().split("## Dados do cliente\n", 1)
    if len(dados) < 2:
        return None
    bloco = dados[1].split("\n## ", 1)[0]
    simples = re.search(r"^Simples Nacional: (.+)$", bloco, re.MULTILINE)
    if simples and "até o momento" in simples.group(1):
        return datetime.date.max
    abertura = re.search(r"^Abertura: (\d{2}/\d{2}/\d{4})$", bloco, re.MULTILINE)
    if not abertura:
        return None
    inicio = datetime.datetime.strptime(abertura.group(1), "%d/%m/%Y").date()
    if simples:
        datas = re.findall(r"\d{2}/\d{2}/\d{4}", simples.group(1))
        if len(datas) >= 2:
            fim = datetime.datetime.strptime(datas[-1], "%d/%m/%Y").date()
            inicio = max(inicio, fim + datetime.timedelta(days=1))
    return inicio


def executar_verificacao_speds(pasta_do_cliente):
    inicio = inicio_contagem_speds(pasta_do_cliente)
    resultado = verificar_speds(pasta_do_cliente, inicio)
    texto = formatar_verificacao(resultado, inicio)
    atualizar_relatorio(pasta_do_cliente, "Verificação de SPEDs", texto)
    total = sum(item["arquivos"] for item in resultado.values())
    faltantes = sum(len(item["faltantes"]) for item in resultado.values())
    log(f"SPEDs verificados: {total} arquivo(s) TXT; {faltantes} período(s) faltante(s).")
    status("Verificação de SPEDs concluída.", "green")
    return total, faltantes
















def executar_fechamento_rar_ma():
    if not pasta_cliente:
        messagebox.showwarning(
            "Atenção", "Selecione a pasta do cliente primeiro (Passo 01)."
        )
        return

    pasta_documentos = obter_pasta_documentos(pasta_cliente, criar=False)
    pasta_ma = os.path.join(pasta_cliente, "PLANILHAS MA")

    caminho_winrar = shutil.which("Rar.exe") or ""

    auditoria_itens = {
        "M800": "M800 - Receitas Isentas, Sem Incidência, Alíquota Zero e Suspensão - Cofins",
        "M400": "M400 - Receitas Isentas, Sem Incidência, Alíquota Zero e Suspensão - PIS",
        "H005, H010": "H005, H010 - Totais e Inventário",
        "H005": "H005 - Totais do Inventário",
        "C500, C505": "C500, C505 - Nota Fiscal de Energia Elétrica, de Água e Gás e Itens - Cofins",
        "C100, C170, 0200": "C100, C170, 0200 - Documentos e Itens - Nota Fiscal",
        "D100": "D100 - Aquisição de Serviços de Transporte",
        "D100, D101": "D100, D101 - Aquisição de Serviços de Transporte e Complemento - PIS",
        "242": "242 - Saídas - Todos os Registros - Completo - Base NCM",
        "240": "240 - Entradas - Todos os Registros - Completo - Base NCM",
        "207": "207 - Total por CFOP - Entradas e Saídas (Todos Registros)",
        "069": "069 - Entradas - Todos os Registros - Completo",
        "063": "063 - Entradas Ativo Imobilizado - EFD-ICMS IPI + EFD-Contribuições",
        "0000, 0010": "0000, 0010 - Identificação PJ e Parâmetros de Tributação",
        "0000": "0000 - Abertura Arquivo Digital e Identificação Pessoa Jurídica",
        "Balancete ECF": "Balancete ECF",
        "Balancete ECD - DÉBITO": "Balancete ECD - DÉBITO",
        "Balancete ECD - SALDO": "Balancete ECD - SALDO (DÉBITO - CRÉDITO)",
    }

    def rotina_completa():
        status("Processando Fechamento...", "orange")
        if os.path.exists(pasta_documentos) and os.path.exists(caminho_winrar):
            log(f"Iniciando compactação das subpastas em {os.path.basename(pasta_documentos)}...")
            subpastas = [
                nome
                for nome in os.listdir(pasta_documentos)
                if os.path.isdir(os.path.join(pasta_documentos, nome))
            ]
            for nome_pasta in subpastas:
                pasta_alvo = os.path.join(pasta_documentos, nome_pasta)
                arquivo_saida = os.path.join(pasta_documentos, f"{nome_pasta}.rar")
                log(f"Compactando: {nome_pasta} ...")
                comando = [
                    caminho_winrar,
                    "a",
                    "-ep1",
                    arquivo_saida,
                    pasta_alvo,
                ]
                try:
                    subprocess.run(
                        comando, check=True, creationflags=subprocess.CREATE_NO_WINDOW
                    )
                except Exception as e:
                    log(f"   Erro ao compactar {nome_pasta}: {e}")

        faltantes = []
        if os.path.exists(pasta_ma):
            itens_encontrados = []
            for _, dirs, files in os.walk(pasta_ma):
                for nome in dirs + files:
                    itens_encontrados.append(normalizar_nome(nome))

            for codigo_busca in auditoria_itens:
                codigo_norm = normalizar_nome(codigo_busca)
                encontrou = any(codigo_norm in item for item in itens_encontrados)
                if codigo_busca == "0000":
                    m_0000 = [i for i in itens_encontrados if "0000" in i]
                    m_0010 = [i for i in itens_encontrados if "00000010" in i]
                    if len(m_0000) == len(m_0010) and len(m_0000) > 0:
                        encontrou = False
                if codigo_busca == "H005":
                    m_h005 = [i for i in itens_encontrados if "h005" in i]
                    m_h010 = [i for i in itens_encontrados if "h005h010" in i]
                    if len(m_h005) == len(m_h010) and len(m_h005) > 0:
                        encontrou = False
                if not encontrou:
                    faltantes.append(codigo_busca)
        else:
            faltantes.append("Pasta PLANILHAS MA ausente")

        itens_presentes = [item for item in auditoria_itens if item not in faltantes]
        conferencia = ("Presentes (pela identificação no nome):\n"
                       + ("\n".join(f"- {item}: {auditoria_itens[item]}" for item in itens_presentes) or "- Nenhum")
                       + "\n\nAusentes:\n"
                       + ("\n".join(f"- {item}" for item in faltantes) or "- Nenhum")
                       + "\n\nA conferência usa nomes de arquivos; não valida o conteúdo fiscal.")
        caminho_relatorio = atualizar_relatorio(pasta_cliente, "Conferência SPED", conferencia)
        log(f"Relatório atualizado: {caminho_relatorio}")

        status("Fechamento Concluído!", "green")
        root.after(
            0,
            lambda: messagebox.showinfo(
                "Fechamento Concluído",
                "Conferência concluída. Verifique RELATORIO_DOCUMENTOS.txt na pasta do cliente.",
            ),
        )

    threading.Thread(target=rotina_completa, daemon=True).start()


def criar_nova_pasta():
    global pasta_cliente, criacao_pasta_em_andamento
    if criacao_pasta_em_andamento:
        return
    nome_cliente = entry_nome_cliente.get().strip()
    if not nome_cliente:
        messagebox.showwarning("Atenção", "Preencha o Nome do cliente.")
        return

    pasta_base = CONFIG_APP.get("pasta_padrao_clientes") or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "CLIENTES"
    )
    caminho_cliente = os.path.join(
        pasta_base, nome_pasta_cliente(nome_cliente, "").rstrip("_")
    )
    criacao_pasta_em_andamento = True
    label_pasta.configure(text="Criando pasta...", text_color="orange")
    btn_iniciar.configure(state="disabled")

    def processo_criacao():
        try:
            os.makedirs(caminho_cliente, exist_ok=True)
            caminho_copy = CONFIG_APP.get("caminho_copypasta", "")
            if caminho_copy and os.path.isdir(caminho_copy):
                shutil.copytree(caminho_copy, caminho_cliente, dirs_exist_ok=True)
            criar_pastas_speds(caminho_cliente)
            atualizar_relatorio(caminho_cliente)
        except Exception as erro:
            log(f"Erro ao criar a pasta do cliente: {erro}")

            def falha(erro=erro):
                global criacao_pasta_em_andamento
                criacao_pasta_em_andamento = False
                if pasta_cliente and os.path.isdir(pasta_cliente):
                    label_pasta.configure(
                        text=f"✔  {os.path.basename(pasta_cliente)}", text_color="green"
                    )
                    btn_iniciar.configure(state="normal")
                else:
                    label_pasta.configure(
                        text="● Nenhuma pasta vinculada", text_color=TXT_MUTED
                    )
                messagebox.showerror("Cliente", f"Não foi possível criar a pasta:\n{erro}")

            root.after(0, falha)
            return

        def concluir():
            global pasta_cliente, criacao_pasta_em_andamento
            pasta_cliente = caminho_cliente
            root.pasta_cliente = caminho_cliente
            criacao_pasta_em_andamento = False
            label_pasta.configure(
                text=f"✔  {os.path.basename(caminho_cliente)}", text_color="green"
            )
            btn_abrir_chrome.configure(state="normal")
            btn_iniciar.configure(state="normal")
            log(f"Pasta do cliente pronta em: {caminho_cliente}")

        root.after(0, concluir)

    threading.Thread(target=processo_criacao, daemon=True).start()


def selecionar_pasta_existente():
    global pasta_cliente
    if criacao_pasta_em_andamento:
        messagebox.showinfo("Cliente", "Aguarde a criação da pasta terminar.")
        return
    pasta_base = filedialog.askdirectory(title="Selecione a pasta do cliente")
    if pasta_base:
        pasta_cliente = pasta_base
        criar_pastas_speds(pasta_cliente)
        label_pasta.configure(
            text=f"✔  {os.path.basename(pasta_base)}", text_color="green"
        )
        btn_abrir_chrome.configure(state="normal")
        btn_iniciar.configure(state="normal")


AVISO_DCTF_INDISPONIVEL = "DCTF indisponível — captação pendente. Realizar nova tentativa."


def atualizar_aviso_dctf_relatorio(pasta_do_cliente, indisponivel=True):
    texto = AVISO_DCTF_INDISPONIVEL if indisponivel else "Indisponibilidade anterior resolvida."
    atualizar_relatorio(pasta_do_cliente, "Captação DCTF Normal", texto)
    return True


def pgdas_tem_arquivos(pasta_do_cliente):
    pasta = os.path.join(
        obter_pasta_documentos(pasta_do_cliente, criar=False), SUBPASTA_PGDAS
    )
    if not os.path.isdir(pasta):
        return False, 0
    qtd = 0
    for _, _, arquivos in os.walk(pasta):
        for nome in arquivos:
            nome_l = nome.lower()
            if not nome.startswith("~$") and nome_l not in ARQUIVOS_IGNORADOS_TEMP and not nome_l.endswith(EXT_DOWNLOAD_INCOMPLETO):
                qtd += 1
    return qtd > 0, qtd


def registrar_pgdas_no_relatorio(pasta_do_cliente):
    tem_pgdas, qtd_pgdas = pgdas_tem_arquivos(pasta_do_cliente)
    atualizar_relatorio(pasta_do_cliente, "Captação PGDAS", f"{qtd_pgdas} arquivo(s) encontrado(s).")
    return tem_pgdas


def agrupar_faltantes(meses_sucesso):
    agora = datetime.datetime.now()
    esperados = []
    for a in range(ANO_INICIO, agora.year + 1):
        max_mes = agora.month if a == agora.year else 12
        for m in range(1, max_mes + 1):
            esperados.append((a, m))

    faltantes = sorted([em for em in esperados if em not in meses_sucesso])
    if not faltantes:
        return []

    grupos, grupo_atual = [], [faltantes[0]]
    for i in range(1, len(faltantes)):
        ano_ant, mes_ant = grupo_atual[-1]
        ano_atu, mes_atu = faltantes[i]
        if (ano_atu * 12 + mes_atu) - (ano_ant * 12 + mes_ant) == 1:
            grupo_atual.append(faltantes[i])
        else:
            grupos.append(grupo_atual)
            grupo_atual = [faltantes[i]]
    grupos.append(grupo_atual)

    return [
        f"SEM REGISTRO:{g[0][1]:02d}-{g[0][0]}"
        if len(g) == 1
        else f"SEM REGISTRO: {g[0][1]:02d}-{g[0][0]} A {g[-1][1]:02d}-{g[-1][0]}"
        for g in grupos
    ]


def retornar_home_ecac(driver, obrigatorio=False):
    """Clica na Home da guia principal e confirma o carregamento do portal."""
    try:
        if not focar_aba_principal_ecac(driver):
            raise RuntimeError("Guia principal do e-CAC não encontrada.")
        driver.switch_to.default_content()
        espera = WebDriverWait(driver, 30)
        btn_home = espera.until(EC.element_to_be_clickable((By.ID, "linkHome")))
        pagina_anterior = driver.find_element(By.TAG_NAME, "html")
        log("Voltando à Home do e-CAC e aguardando o carregamento...")
        driver.execute_script("arguments[0].click();", btn_home)
        espera.until(EC.staleness_of(pagina_anterior))
        espera.until(lambda d: (
            _url_do_ecac(d.current_url)
            and d.current_url.split("?", 1)[0].split("#", 1)[0].lower().endswith("/default.aspx")
            and d.execute_script("return document.readyState") == "complete"
        ))
        espera.until(EC.visibility_of_element_located((By.ID, "informacao-perfil")))
        espera.until(EC.element_to_be_clickable((By.ID, "btnPerfil")))
        log("✔ Home do e-CAC carregada e pronta.")
        return True
    except Exception as erro:
        if obrigatorio:
            raise RuntimeError("Não foi possível confirmar a Home do e-CAC.") from erro
        log("⚠ Não foi possível retornar ao Home do e-CAC automaticamente.")
        return False

# ─────────────────────────────────────────────────────────────────
# ORQUESTRADOR DE MÓDULOS PARA A PASTA SELECIONADA
# ─────────────────────────────────────────────────────────────────
def _iniciar_automacao_modulo(tipo_selecionado=None, pasta_alvo=None):
    """Inicia o fluxo principal de automação (Sem pop-ups, com retorno ao Home e trava Anti-Timeout)."""
    global driver_global, deve_parar, automacao_em_andamento, pasta_cliente
    global root, btn_iniciar, btn_abrir_chrome, btn_reiniciar, tipos_perdcomp_selecionados

    automacao_em_andamento = True  # Bloqueia o anti-timeout durante a captura.
    pasta_temp = pasta_temporaria()
    if pasta_alvo:
        pasta_cliente = pasta_alvo
    if not tipo_selecionado:
        raise ValueError("Módulo não informado.")

    root.after(0, lambda: btn_iniciar.configure(state="disabled"))
    root.after(0, lambda: btn_abrir_chrome.configure(state="disabled"))
    root.after(0, lambda: btn_reiniciar.configure(state="normal"))

    try:
        log(f"Iniciando Módulo: {tipo_selecionado}")
        status("Conectando...", "orange")

        if driver_global is None:
            raise RuntimeError("Chrome não conectado. Abra e autentique o e-CAC antes de iniciar.")

        driver = driver_global

        caminho_absoluto = os.path.abspath(pasta_temp)
        driver.execute_cdp_cmd(
            "Browser.setDownloadBehavior",
            {
                "behavior": "allow",
                "downloadPath": caminho_absoluto,
                "eventsEnabled": True,
            },
        )

        if (
            "autenticacao" in driver.current_url.lower()
            or "login" in driver.current_url.lower()
        ):
            log("⚠ Atenção: Faça o login no eCAC antes de iniciar a automação.")
            root.after(0, lambda: btn_iniciar.configure(state="normal"))
            root.after(0, lambda: btn_abrir_chrome.configure(state="normal"))
            raise RuntimeError("Sessão do e-CAC não autenticada.")

        total_baixados = 0
        meses_sucesso = set()

        if tipo_selecionado in ["DCTF Normal", "DCTF normal"]:
            if not navegar_para_dctf(driver):
                raise RuntimeError("Não foi possível abrir a DCTF Normal.")
            total_baixados, meses_sucesso = processar_dctf_normal(driver, pasta_temp, tipo_selecionado)

        elif tipo_selecionado == "DCTF-Web":
            aba_ecac = focar_aba_principal_ecac(driver)
            try:
                if localizar_tela_dctfweb(driver) or navegar_para_dctf_web(driver):
                    log("✔ Tela da DCTF-Web detectada com sucesso!")
                    total_baixados, meses_sucesso = processar_dctf_web(driver, pasta_temp, tipo_selecionado)
                else:
                    raise RuntimeError("Tela DCTF-Web não encontrada.")
            finally:
                fechar_abas_dctfweb(driver, aba_ecac)

        elif tipo_selecionado == "PER/DCOMP":
            if navegar_para_perdcomp(driver):
                log("✔ Tela do PER/DCOMP detectada com sucesso!")
                total_baixados, meses_sucesso = processar_perdcomp(driver, pasta_temp, tipo_selecionado)
            else:
                log("✘ O robô não achou a tela do PER/DCOMP. Navegue até 'Documentos Entregues' e tente novamente.")
                raise RuntimeError("Tela PER/DCOMP não encontrada.")

        elif tipo_selecionado == "PGDAS":
            navegar_para_pgdas(driver)
            total_baixados, meses_sucesso = processar_pgdas(driver, pasta_temp, tipo_selecionado)

        elif tipo_selecionado == "DARF":
            log("Navegue manualmente até o painel de pesquisa do DARF na tela do Sicalc Web / eCAC.")
            total_baixados, meses_sucesso = processar_darf(driver, pasta_temp, tipo_selecionado)

        # =====================================================================
        # RETORNO AO HOME APÓS A CAPTAÇÃO (Deixa o e-CAC pronto para a próx. tarefa)
        # =====================================================================
        retornar_home_ecac(driver)

        lista_de_falhas = agrupar_faltantes(meses_sucesso)

        log(f"\n{'─'*50}")
        log("✔ CONCLUÍDO — Processo finalizado com sucesso.")

        # =====================================================================
        # EXIBIÇÃO DE RESULTADOS APENAS NO LOG (SEM MESSAGEBOX)
        # =====================================================================
        if tipo_selecionado in ["DCTF Normal", "DCTF normal", "DCTF-Web"]:
            if lista_de_falhas:
                status("Concluído com avisos.", "orange")
                atualizar_relatorio(pasta_cliente, f"Captação {tipo_selecionado}",
                    f"{total_baixados} arquivo(s) baixado(s).\nPendências:\n" + "\n".join(f"- {item}" for item in lista_de_falhas))
                
                log(f"⚠ FALTANTES IDENTIFICADOS ({total_baixados} baixados):")
                if isinstance(lista_de_falhas, list):
                    for falha in lista_de_falhas:
                        log(f"  ➜ {falha}")
                else:
                    log(f"  ➜ {lista_de_falhas}")
            else:
                if tipo_selecionado in ["DCTF Normal", "DCTF normal"]:
                    atualizar_aviso_dctf_relatorio(pasta_cliente, indisponivel=False)
                status("Concluído!", "green")
                atualizar_relatorio(pasta_cliente, f"Captação {tipo_selecionado}", f"Histórico completo. {total_baixados} arquivo(s) baixado(s).")
                log(f"✔ HISTÓRICO COMPLETO! Total: {total_baixados} arquivos.")

        elif tipo_selecionado == "PER/DCOMP":
            caminho_obs = os.path.join(pasta_cliente, "obs.txt")
            n_falhas = 0
            try:
                with open(caminho_obs, "r", encoding="utf-8") as f_obs:
                    conteudo = f_obs.read()
                ultimo_bloco = conteudo.rsplit("AUDITORIA PER/DCOMP", 1)
                if len(ultimo_bloco) > 1:
                    for linha in ultimo_bloco[1].splitlines():
                        if "Falhas" in linha:
                            n_falhas = int("".join(filter(str.isdigit, linha)) or "0")
                            break
            except Exception:
                pass

            if n_falhas > 0:
                status("Concluído com falhas.", "orange")
                log(f"⚠ PER/DCOMP finalizado com {n_falhas} documento(s) não confirmado(s)! Total salvo: {total_baixados} arquivo(s).")
            else:
                status("Mapeamento concluído.", "green")
                log(f"✔ PER/DCOMP FINALIZADO! Total: {total_baixados} arquivo(s) salvos sem falhas.")

        elif tipo_selecionado in ["PGDAS", "DARF"]:
            status("Mapeamento concluído.", "green")
            log(f"✔ Processo do {tipo_selecionado} FINALIZADO! Total: {total_baixados} arquivos baixados.")
        else:
            status("Mapeamento concluído.", "green")

        if tipo_selecionado not in ["DCTF Normal", "DCTF normal", "DCTF-Web"]:
            atualizar_relatorio(
                pasta_cliente, f"Captação {tipo_selecionado}",
                f"{total_baixados} arquivo(s) baixado(s)."
                + (f"\nFalhas não confirmadas: {n_falhas}." if tipo_selecionado == "PER/DCOMP" else ""),
            )

    except DctfIndisponivel:
        atualizar_aviso_dctf_relatorio(pasta_cliente)
        status("DCTF indisponível; captação pendente.", "orange")
        raise
    except Exception as erro:
        if "interrompida" in str(erro).lower():
            log("\n[!] Automação Parada com Sucesso.")
            status("Parado.", "gray")
        else:
            log(f"\n✘ Erro: {erro}")
            status("Erro.", "red")
        raise

    finally:
        automacao_em_andamento = False  # <-- DESTRAVA: Libera a função de 5 minutos novamente
        limpar_pasta_temp(pasta_temp)
        if not deve_parar:
            try:
                root.after(0, lambda: btn_iniciar.configure(state="normal"))
                root.after(0, lambda: btn_abrir_chrome.configure(state="normal"))
            except:
                pass

            
def iniciar_automacao(modulos_escolhidos, pasta_alvo):
    """Executa os módulos escolhidos na pasta selecionada."""
    for modulo in modulos_escolhidos:
        verificar_parada()
        try:
            _iniciar_automacao_modulo(modulo, pasta_alvo)
        except DctfIndisponivel:
            log("DCTF indisponível; seguindo para o próximo módulo.")


def nome_pasta_cliente(nome, cnpj):
    nome_seguro = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nome).strip(" .")
    return f"{nome_seguro[:90] or 'Empresa'}_{cnpj}"


def normalizar_cnpj(valor):
    cnpj = re.sub(r"\D", "", str(valor or ""))
    return cnpj if len(cnpj) == 14 else ""


def ao_clicar_iniciar():
    global execucao_em_andamento, deve_parar
    if execucao_em_andamento:
        return
    if criacao_pasta_em_andamento:
        messagebox.showinfo("Cliente", "Aguarde a criação da pasta terminar.")
        return
    if not pasta_cliente or not os.path.isdir(pasta_cliente):
        messagebox.showwarning("Cliente", "Crie ou selecione a pasta do cliente antes de iniciar.")
        return
    escolhido = root.modulo_selecionado.get()
    modulos = MODULOS_CAPTACAO_LOCAL if escolhido == "Todos os módulos" else (escolhido,)
    pasta_alvo = pasta_cliente
    if not conectar_chrome_autenticado():
        return
    deve_parar = False
    execucao_em_andamento = True
    txt_log.configure(state="normal")
    txt_log.delete("1.0", "end")
    txt_log.configure(state="disabled")

    def executar():
        global execucao_em_andamento
        try:
            iniciar_automacao(modulos, pasta_alvo)
        except Exception as erro:
            if not deve_parar:
                log(f"Execução interrompida: {erro}")
                status("Execução interrompida", "red")
        finally:
            execucao_em_andamento = False
            root.after(0, lambda: btn_reiniciar.configure(state="disabled"))

    threading.Thread(target=executar, daemon=True).start()


# ─────────────────────────────────────────────────────────────────
# Tipografia e paleta da interface
# ─────────────────────────────────────────────────────────────────
FONT_DISPLAY = ("Cascadia Code", 20, "bold")
FONT_SERIF_TITLE = ("Cascadia Code", 13, "bold")
FONT_SERIF_BODY = ("Cascadia Code", 12)
FONT_SANS_BOLD = ("Cascadia Code", 12, "bold")
FONT_SANS = ("Cascadia Code", 10)
FONT_MONO = ("Cascadia Code", 12)

BG_ROOT = ("#F4F4F0", "#121212")
BG_CARD = ("#FFFFFF", "#1A1A1A")
BG_ELEVATED = ("#ECECE6", "#242424")
BORDER_SUBTLE = ("#D8D8D0", "#333333")

TXT_PRIMARY = ("#111111", "#F0F0F0")
TXT_MUTED = ("#555555", "#AAAAAA")

ACCENT_PRIMARY = ("#1C1C1C", "#E0E0E0")
ACCENT_HOVER = ("#333333", "#FFFFFF")

BTN_NEUTRAL = ("#E4E4DE", "#2A2A2A")
BTN_NEUTRAL_HOVER = ("#D4D4CE", "#383838")

COLOR_STOP = ("#D93636", "#E64848")
HOVER_STOP = ("#B92525", "#D13232")

COLOR_WARN = ("#E5A000", "#F0B323")
HOVER_WARN = ("#C88900", "#D99B12")

COLOR_SYNC = ("#20A464", "#2DBD78")
HOVER_SYNC = ("#16834F", "#209D62")

TXT_TITULO = TXT_PRIMARY
TXT_SECUNDARIO = TXT_MUTED
BORDER_COLOR = BORDER_SUBTLE
COR_PRINCIPAL = ACCENT_PRIMARY
HOVER_PRI = ACCENT_HOVER
BG_BTN_SEC = BTN_NEUTRAL
TXT_BTN_SEC = TXT_PRIMARY
HOVER_SEC = BTN_NEUTRAL_HOVER

LARGURA_JANELA = 760
ALTURA_NORMAL = 735
ALTURA_PERDCOMP = 775

ALTURA_LOG_NORMAL = 135
ALTURA_LOG_PERDCOMP = 75

ctk.set_appearance_mode("Dark")


class InterfaceExclusivaECAC(ctk.CTk):
    def __init__(self):
        global root
        super().__init__()
        self.title("Automação Fiscal — eCAC")
        self.geometry(f"{LARGURA_JANELA}x{ALTURA_NORMAL}")
        self.resizable(False, False)
        self.configure(fg_color=BG_ROOT)
        self._centralizar_janela(LARGURA_JANELA, ALTURA_NORMAL)
        self.pasta_cliente = None

        self.modulos_vars = {
            "DARF": ctk.BooleanVar(value=True),
            "DCTF Normal": ctk.BooleanVar(value=False),
            "DCTF-Web": ctk.BooleanVar(value=False),
            "PER/DCOMP": ctk.BooleanVar(value=False),
            "PGDAS": ctk.BooleanVar(value=False),
        }

        self.tipos_perdcomp_selecionados = {
            "Declaração de Compensação": ctk.BooleanVar(value=True),
            "Pedido de Restituição": ctk.BooleanVar(value=True),
            "Pedido de Ressarcimento": ctk.BooleanVar(value=True),
            "Pedido de Reembolso": ctk.BooleanVar(value=True),
        }

        self.main_wrap = ctk.CTkFrame(self, fg_color="transparent")
        self.main_wrap.pack(fill="both", expand=True, padx=16, pady=14)
        self._construir_cabecalho()
        self._construir_secao_1_cliente()
        self._construir_secao_2_speds()
        self._construir_secao_3_execucao()
        self._construir_secao_log_compacto()
        self._conectar_rotinas_existentes()

    def _conectar_rotinas_existentes(self):
        global root, entry_nome_cliente, label_pasta, btn_abrir_chrome
        global btn_iniciar, btn_reiniciar, txt_log, label_status
        global tipos_perdcomp_selecionados, modulos_selecionados_vars

        root = self
        entry_nome_cliente = self.entry_nome_cliente
        label_pasta = self.label_pasta
        btn_abrir_chrome = self.btn_abrir_chrome
        btn_iniciar = self.btn_iniciar
        btn_reiniciar = self.btn_reiniciar
        txt_log = self.txt_log
        label_status = self.label_status
        tipos_perdcomp_selecionados = self.tipos_perdcomp_selecionados
        modulos_selecionados_vars = self.modulos_vars
        self.btn_abrir_chrome.configure(state="normal")
        self.btn_iniciar.configure(state="disabled")
        self.btn_reiniciar.configure(state="disabled")

    def _centralizar_janela(self, largura, altura):
        self.update_idletasks()
        x = int((self.winfo_screenwidth() / 2) - (largura / 2))
        y = int((self.winfo_screenheight() / 2) - (altura / 2))
        self.geometry(f"{largura}x{altura}+{x}+{y}")

    def _redimensionar_altura_janela(self, nova_altura):
        self.update_idletasks()
        x = self.winfo_x()
        y = self.winfo_y()
        self.geometry(f"{LARGURA_JANELA}x{nova_altura}+{x}+{y}")

    def _criar_painel(self, parent):
        painel = ctk.CTkFrame(
            parent,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        painel.pack(fill="x", pady=(0, 8))
        return painel

    # ─────────────────────────────────────────────────────────────
    # CABEÇALHO EDITORIAL
    # ─────────────────────────────────────────────────────────────
    def _construir_cabecalho(self):
        header = self._criar_painel(self.main_wrap)
        inner = ctk.CTkFrame(header, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        badge = ctk.CTkFrame(
            inner, width=40, height=40, corner_radius=8, fg_color=ACCENT_PRIMARY
        )
        badge.pack(side="left", padx=(0, 12))
        badge.pack_propagate(False)
        ctk.CTkLabel(
            badge, text="§", font=("Cascadia Code", 22, "bold"), text_color=BG_CARD
        ).place(relx=0.5, rely=0.5, anchor="center")

        txt_box = ctk.CTkFrame(inner, fg_color="transparent")
        txt_box.pack(side="left", fill="y")
        ctk.CTkLabel(
            txt_box,
            text="Canivete Suíço Fiscal — eCAC",
            font=FONT_DISPLAY,
            text_color=TXT_PRIMARY,
        ).pack(anchor="w")
        ctk.CTkLabel(
            txt_box,
            text="Captação e gestão de documentos fiscais.",
            font=FONT_SERIF_BODY,
            text_color=TXT_MUTED,
        ).pack(anchor="w")

        ctrl_box = ctk.CTkFrame(inner, fg_color="transparent")
        ctrl_box.pack(side="right")
        self.btn_tema = ctk.CTkButton(
            ctrl_box,
            text="☀ Claro",
            width=80,
            height=30,
            fg_color=BTN_NEUTRAL,
            hover_color=BTN_NEUTRAL_HOVER,
            text_color=TXT_PRIMARY,
            font=FONT_SANS_BOLD,
            corner_radius=6,
            command=self._alternar_tema,
        )
        self.btn_tema.pack(side="right", padx=(6, 0))
        ctk.CTkButton(
            ctrl_box,
            text="⚙ Ajustes",
            width=88,
            height=30,
            fg_color=BTN_NEUTRAL,
            hover_color=BTN_NEUTRAL_HOVER,
            text_color=TXT_PRIMARY,
            font=FONT_SANS_BOLD,
            corner_radius=6,
            command=self._abrir_janela_configuracao,
        ).pack(side="right")

    # ─────────────────────────────────────────────────────────────
    # SEÇÃO 01: IDENTIFICAÇÃO DO CLIENTE
    # ─────────────────────────────────────────────────────────────
    def _construir_secao_1_cliente(self):
        painel = self._criar_painel(self.main_wrap)
        topo = ctk.CTkFrame(painel, fg_color="transparent")
        topo.pack(fill="x", padx=16, pady=(10, 6))
        ctk.CTkLabel(
            topo,
            text="01 · Identificação do Cliente",
            font=FONT_SERIF_TITLE,
            text_color=TXT_PRIMARY,
        ).pack(side="left")
        self.label_pasta = ctk.CTkLabel(
            topo,
            text="● Nenhuma pasta vinculada",
            font=FONT_SANS_BOLD,
            text_color=TXT_MUTED,
        )
        self.label_pasta.pack(side="right")

        grid = ctk.CTkFrame(painel, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(0, 12))
        grid.grid_columnconfigure((0, 1), weight=1)

        # Coluna Esquerda: Opções A e B
        col_esq = ctk.CTkFrame(grid, fg_color="transparent")
        col_esq.grid(row=0, column=0, sticky="nsew")
        ctk.CTkLabel(
            col_esq,
            text="Criar nova estrutura",
            font=FONT_SANS_BOLD,
            text_color=TXT_MUTED,
        ).pack(anchor="w", pady=(0, 3))
        linha_nova = ctk.CTkFrame(col_esq, fg_color="transparent")
        linha_nova.pack(fill="x", pady=(0, 8))
        self.entry_nome_cliente = ctk.CTkEntry(
            linha_nova,
            height=32,
            font=FONT_SANS,
            fg_color=BG_ELEVATED,
            border_color=BORDER_SUBTLE,
            text_color=TXT_PRIMARY,
            placeholder_text="Razão social ou nome da pasta...",
            corner_radius=6,
        )
        self.entry_nome_cliente.pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            linha_nova,
            text="Criar Pasta",
            width=100,
            height=32,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            text_color=BG_CARD,
            font=FONT_SANS_BOLD,
            corner_radius=6,
            command=self._acao_criar_pasta,
        ).pack(side="right")

        ctk.CTkLabel(
            col_esq,
            text="Diretório existente",
            font=FONT_SANS_BOLD,
            text_color=TXT_MUTED,
        ).pack(anchor="w", pady=(0, 3))
        ctk.CTkButton(
            col_esq,
            text="📁 Selecionar Pasta existente",
            height=32,
            fg_color=BTN_NEUTRAL,
            hover_color=BTN_NEUTRAL_HOVER,
            text_color=TXT_PRIMARY,
            font=FONT_SANS_BOLD,
            corner_radius=6,
            command=self._acao_selecionar_pasta,
        ).pack(fill="x")

        consulta = ctk.CTkFrame(
            grid, fg_color=BG_ELEVATED, corner_radius=8,
            border_width=1, border_color=BORDER_SUBTLE,
        )
        consulta.grid(row=0, column=1, sticky="nsew", padx=(18, 0))
        ctk.CTkLabel(
            consulta, text="Consulta de CNPJ", font=FONT_SANS_BOLD,
            text_color=TXT_PRIMARY,
        ).pack(anchor="w", padx=12, pady=(12, 4))
        ctk.CTkLabel(
            consulta, text="Define abertura e histórico do Simples.",
            font=FONT_SANS, text_color=TXT_MUTED,
        ).pack(anchor="w", padx=12)
        linha_consulta = ctk.CTkFrame(consulta, fg_color="transparent")
        linha_consulta.pack(fill="x", padx=12, pady=(10, 12))
        self.entry_cnpj_sped = ctk.CTkEntry(
            linha_consulta, placeholder_text="Digite os 14 números...",
            height=32, font=FONT_SANS, fg_color=BG_CARD,
        )
        self.entry_cnpj_sped.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self.btn_consultar_cnpj_sped = ctk.CTkButton(
            linha_consulta, text="Consultar", width=95, height=32,
            fg_color=BTN_NEUTRAL, hover_color=BTN_NEUTRAL_HOVER,
            text_color=TXT_PRIMARY, font=FONT_SANS_BOLD,
            command=self._acao_consultar_cnpj_sped,
        )
        self.btn_consultar_cnpj_sped.pack(side="left")

    def _construir_secao_2_speds(self):
        painel = self._criar_painel(self.main_wrap)
        ctk.CTkLabel(
            painel, text="02 · Configuração do Módulo", font=FONT_SERIF_TITLE,
            text_color=TXT_PRIMARY,
        ).pack(anchor="w", padx=16, pady=(10, 6))
        linha = ctk.CTkFrame(painel, fg_color="transparent")
        linha.pack(fill="x", padx=16, pady=(0, 10))
        self.modulo_selecionado = ctk.StringVar(value="Todos os módulos")
        ctk.CTkOptionMenu(
            linha, values=["Todos os módulos", *MODULOS_CAPTACAO_LOCAL],
            variable=self.modulo_selecionado, width=320, height=32,
            fg_color=BG_ELEVATED, button_color=BTN_NEUTRAL,
            button_hover_color=BTN_NEUTRAL_HOVER,
            text_color=TXT_PRIMARY, font=FONT_SANS,
        ).pack(side="left", padx=(0, 12))
        self.label_contagem_speds = ctk.CTkLabel(
            linha, text="SPEDs ainda não verificados", font=FONT_SANS,
            text_color=TXT_MUTED,
        )
        self.label_contagem_speds.pack(side="left")
        self.btn_verificar_speds = ctk.CTkButton(
            linha, text="Verificar SPEDs", width=145, height=32,
            fg_color=BTN_NEUTRAL, hover_color=BTN_NEUTRAL_HOVER,
            text_color=TXT_PRIMARY, font=FONT_SANS_BOLD,
            command=self._acao_verificar_speds,
        )
        self.btn_verificar_speds.pack(side="right")

    # ─────────────────────────────────────────────────────────────
    # SEÇÃO 03: EXECUÇÃO E UTILITÁRIOS
    # ─────────────────────────────────────────────────────────────
    def _construir_secao_3_execucao(self):
        painel = self._criar_painel(self.main_wrap)
        ctk.CTkLabel(
            painel,
            text="03 · Execução e Utilitários",
            font=FONT_SERIF_TITLE,
            text_color=TXT_PRIMARY,
        ).pack(anchor="w", padx=16, pady=(10, 6))
        barra = ctk.CTkFrame(painel, fg_color="transparent")
        barra.pack(fill="x", padx=16, pady=(0, 12))
        barra.grid_columnconfigure((0, 1, 2, 3, 4), weight=1)

        self.btn_abrir_chrome = ctk.CTkButton(
            barra,
            text="🌐 Chrome",
            height=36,
            fg_color=BTN_NEUTRAL,
            hover_color=BTN_NEUTRAL_HOVER,
            text_color=TXT_PRIMARY,
            font=FONT_SANS_BOLD,
            corner_radius=6,
            state="disabled",
            command=self._acao_abrir_chrome,
        )
        self.btn_abrir_chrome.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        self.btn_iniciar = ctk.CTkButton(
            barra,
            text="▶ Iniciar",
            height=36,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            text_color=BG_CARD,
            font=FONT_SANS_BOLD,
            corner_radius=6,
            state="disabled",
            command=ao_clicar_iniciar,
        )
        self.btn_iniciar.grid(row=0, column=1, sticky="ew", padx=3)

        self.btn_reiniciar = ctk.CTkButton(
            barra,
            text="🛑 Parar",
            height=36,
            fg_color=COLOR_STOP,
            hover_color=HOVER_STOP,
            text_color="#FFFFFF",
            font=FONT_SANS_BOLD,
            corner_radius=6,
            state="disabled",
            command=parar_e_reiniciar,
        )
        self.btn_reiniciar.grid(row=0, column=2, sticky="ew", padx=3)

        self.btn_rar = ctk.CTkButton(
            barra,
            text="📦 .Finalizar",
            height=36,
            fg_color=COLOR_WARN,
            hover_color=HOVER_WARN,
            text_color="#FFFFFF",
            font=FONT_SANS_BOLD,
            corner_radius=6,
            command=executar_fechamento_rar_ma,
        )
        self.btn_rar.grid(row=0, column=3, sticky="ew", padx=3)


    # ─────────────────────────────────────────────────────────────
    # SEÇÃO 04: REGISTRO DE ATIVIDADES
    # ─────────────────────────────────────────────────────────────
    def _construir_secao_log_compacto(self):
        self.painel_log = ctk.CTkFrame(
            self.main_wrap,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        self.painel_log.pack(side="bottom", fill="both", expand=True)
        header_log = ctk.CTkFrame(self.painel_log, fg_color="transparent")
        header_log.pack(fill="x", padx=16, pady=(8, 4))
        ctk.CTkLabel(
            header_log,
            text="Registro de Atividades",
            font=FONT_SERIF_TITLE,
            text_color=TXT_PRIMARY,
        ).pack(side="left")
        self.label_status = ctk.CTkLabel(
            header_log,
            text="Pronto para operação",
            font=FONT_SANS,
            text_color=TXT_MUTED,
        )
        self.label_status.pack(side="right")
        self.txt_log = ctk.CTkTextbox(
            self.painel_log,
            height=ALTURA_LOG_NORMAL,
            font=FONT_MONO,
            fg_color=BG_ROOT,
            text_color=TXT_PRIMARY,
            border_color=BORDER_SUBTLE,
            border_width=1,
            corner_radius=6,
        )
        self.txt_log.pack(fill="both", expand=True, padx=16, pady=(0, 10))
        self._registrar_log(
            "Ambiente pronto. Selecione a pasta do cliente no passo 01."
        )

    # ─────────────────────────────────────────────────────────────
    # MODAL DE CONFIGURAÇÕES
    # ─────────────────────────────────────────────────────────────
    def _abrir_janela_configuracao(self):
        janela_config = ctk.CTkToplevel(self)
        janela_config.title("Configurações do Sistema")
        janela_config.geometry("560x430")
        janela_config.resizable(False, False)
        janela_config.transient(self)
        janela_config.grab_set()
        janela_config.configure(fg_color=BG_ROOT)
        janela_config.update_idletasks()
        x = int((janela_config.winfo_screenwidth() / 2) - (560 / 2))
        y = int((janela_config.winfo_screenheight() / 2) - (430 / 2))
        janela_config.geometry(f"+{x}+{y}")

        card = ctk.CTkFrame(
            janela_config,
            fg_color=BG_CARD,
            corner_radius=10,
            border_width=1,
            border_color=BORDER_SUBTLE,
        )
        card.pack(fill="both", expand=True, padx=14, pady=14)
        ctk.CTkLabel(
            card,
            text="Configurações locais",
            font=FONT_DISPLAY,
            text_color=TXT_PRIMARY,
        ).pack(anchor="w", padx=18, pady=(16, 10))

        campos = [
            ("pasta_temp", "Pasta Oculta de Downloads (Temp):", "dir"),
            ("caminho_copypasta", "Caminho do Modelo (Copypasta):", "dir"),
            ("pasta_padrao_clientes", "Pasta Padrão para Novos Clientes:", "dir"),
        ]
        self.entries_config = []
        for chave, rotulo, tipo in campos:
            ctk.CTkLabel(
                card, text=rotulo, font=FONT_SANS_BOLD, text_color=TXT_PRIMARY
            ).pack(anchor="w", padx=18, pady=(4, 2))
            linha = ctk.CTkFrame(card, fg_color="transparent")
            linha.pack(fill="x", padx=18, pady=(0, 6))
            entry = ctk.CTkEntry(
                linha,
                height=30,
                font=FONT_SANS,
                fg_color=BG_ELEVATED,
                text_color=TXT_PRIMARY,
                border_color=BORDER_SUBTLE,
                corner_radius=6,
            )
            entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
            entry.insert(0, CONFIG_APP.get(chave, ""))
            self.entries_config.append(entry)
            cmd = (
                (lambda e=entry: self._procurar_arquivo(e))
                if tipo == "file"
                else (lambda e=entry: self._procurar_pasta(e))
            )
            ctk.CTkButton(
                linha,
                text="Procurar",
                width=90,
                height=30,
                fg_color=BTN_NEUTRAL,
                hover_color=BTN_NEUTRAL_HOVER,
                text_color=TXT_PRIMARY,
                font=FONT_SANS_BOLD,
                corner_radius=6,
                command=cmd,
            ).pack(side="right")

        ctk.CTkFrame(card, fg_color=BORDER_SUBTLE, height=1).pack(
            fill="x", padx=18, pady=(10, 10)
        )
        rodape = ctk.CTkFrame(card, fg_color="transparent")
        rodape.pack(fill="x", padx=18, pady=(0, 12))
        ctk.CTkButton(
            rodape,
            text="Salvar Preferências",
            height=34,
            fg_color=ACCENT_PRIMARY,
            hover_color=ACCENT_HOVER,
            text_color=BG_CARD,
            font=FONT_SANS_BOLD,
            corner_radius=6,
            command=lambda: self._salvar_configuracao(janela_config),
        ).pack(side="right")
        ctk.CTkButton(
            rodape,
            text="Cancelar",
            height=34,
            fg_color="transparent",
            hover_color=BTN_NEUTRAL_HOVER,
            text_color=TXT_MUTED,
            font=FONT_SANS_BOLD,
            corner_radius=6,
            command=janela_config.destroy,
        ).pack(side="right", padx=(0, 8))

    def _salvar_configuracao(self, janela_config):
        pasta_temp, copypasta, pasta_clientes = (
            entrada.get().strip() for entrada in self.entries_config
        )
        if not pasta_temp:
            messagebox.showwarning(
                "Configurações", "Informe uma pasta para os downloads temporários."
            )
            return
        novas_configuracoes = CONFIG_APP.copy()
        novas_configuracoes.update(
            {
                "pasta_temp": pasta_temp,
                "caminho_copypasta": copypasta,
                "pasta_padrao_clientes": pasta_clientes,
            }
        )
        try:
            os.makedirs(pasta_temp, exist_ok=True)
            salvar_config(novas_configuracoes)
        except OSError as erro:
            log(f"Erro ao salvar configurações: {erro}")
            return
        CONFIG_APP.update(novas_configuracoes)
        janela_config.destroy()
        status("Configurações atualizadas.", "green")
        log("Preferências salvas.")

    # ─────────────────────────────────────────────────────────────
    # INTERAÇÕES E REDIMENSIONAMENTO DINÂMICO
    # ─────────────────────────────────────────────────────────────
    def _alternar_painel_perdcomp(self):
        if self.modulos_vars["PER/DCOMP"].get():
            self.frame_tipos_perdcomp.pack(fill="x", padx=16, pady=(0, 10))
            self.txt_log.configure(height=ALTURA_LOG_PERDCOMP)
            self._redimensionar_altura_janela(ALTURA_PERDCOMP)
            self._registrar_log(
                "Módulo PER/DCOMP marcado — filtros de documentos exibidos."
            )
        else:
            self.frame_tipos_perdcomp.pack_forget()
            self.txt_log.configure(height=ALTURA_LOG_NORMAL)
            self._redimensionar_altura_janela(ALTURA_NORMAL)

    def _procurar_arquivo(self, entry):
        caminho = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if caminho:
            entry.delete(0, "end")
            entry.insert(0, caminho)

    def _procurar_pasta(self, entry):
        caminho = filedialog.askdirectory()
        if caminho:
            entry.delete(0, "end")
            entry.insert(0, caminho)

    def _acao_criar_pasta(self):
        if execucao_em_andamento:
            messagebox.showwarning("Cliente", "Aguarde a captação terminar antes de trocar de pasta.")
            return
        criar_nova_pasta()

    def _acao_selecionar_pasta(self):
        if execucao_em_andamento:
            messagebox.showwarning("Cliente", "Aguarde a captação terminar antes de trocar de pasta.")
            return
        selecionar_pasta_existente()
        self.pasta_cliente = pasta_cliente

    def _acao_consultar_cnpj_sped(self):
        if not pasta_cliente:
            messagebox.showwarning("CNPJ", "Selecione a pasta do cliente primeiro.")
            return
        cnpj = normalizar_cnpj(self.entry_cnpj_sped.get())
        if not cnpj:
            messagebox.showwarning("CNPJ", "Informe um CNPJ com 14 dígitos.")
            return
        self.btn_consultar_cnpj_sped.configure(state="disabled")
        cliente = pasta_cliente

        def consultar():
            try:
                dados = consultar_cnpj_api(cnpj)
                atualizar_dados_cnpj_cliente(cnpj, cliente, dados)
                status("Consulta de CNPJ concluída.", "green")
            except Exception as erro:
                log(f"Falha na consulta de CNPJ: {erro}")
                status("Falha na consulta de CNPJ.", "red")
            finally:
                self.after(0, lambda: self.btn_consultar_cnpj_sped.configure(state="normal"))

        threading.Thread(target=consultar, daemon=True).start()

    def _acao_verificar_speds(self):
        if not pasta_cliente:
            messagebox.showwarning("SPEDs", "Selecione a pasta do cliente primeiro.")
            return
        self.btn_verificar_speds.configure(state="disabled")
        cliente = pasta_cliente

        def verificar():
            try:
                total, faltantes = executar_verificacao_speds(cliente)
                resumo = (f"SPEDs: {total} arquivo(s) TXT; {faltantes} período(s) faltante(s)"
                          if inicio_contagem_speds(cliente) is not None
                          else f"SPEDs: {total} arquivo(s) TXT; consulte o CNPJ para calcular faltantes")
                self.after(0, lambda: self.label_contagem_speds.configure(
                    text=resumo
                ))
            except Exception as erro:
                log(f"Falha na verificação dos SPEDs: {erro}")
                status("Falha na verificação dos SPEDs.", "red")
            finally:
                self.after(0, lambda: self.btn_verificar_speds.configure(state="normal"))

        threading.Thread(target=verificar, daemon=True).start()

    def _acao_abrir_chrome(self):
        self.btn_abrir_chrome.configure(state="disabled")

        def abrir():
            try:
                abrir_chrome_debug()
            finally:
                self.after(
                    0, lambda: self.btn_abrir_chrome.configure(state="normal")
                )

        threading.Thread(target=abrir, daemon=True).start()


    def _atualizar_contador_perdcomp(self):
        marcados = sum(
            1 for v in self.tipos_perdcomp_selecionados.values() if v.get()
        )
        total = len(self.tipos_perdcomp_selecionados)
        self.btn_selecionar_todos.configure(
            text=f"Selecionar Todos ({marcados}/{total})"
        )

    def _selecionar_todos_perdcomp(self):
        novo_estado = not all(
            v.get() for v in self.tipos_perdcomp_selecionados.values()
        )
        for var in self.tipos_perdcomp_selecionados.values():
            var.set(novo_estado)
        self._atualizar_contador_perdcomp()

    def _alternar_tema(self):
        if ctk.get_appearance_mode() == "Dark":
            ctk.set_appearance_mode("Light")
            self.btn_tema.configure(text="🌙 Escuro")
        else:
            ctk.set_appearance_mode("Dark")
            self.btn_tema.configure(text="☀ Claro")

    def _registrar_log(self, mensagem):
        hora = datetime.datetime.now().strftime("%H:%M:%S")
        self.txt_log.configure(state="normal")
        self.txt_log.insert("end", f"[{hora}] {mensagem}\n")
        self.txt_log.see("end")
        self.txt_log.configure(state="disabled")


if __name__ == "__main__":
    app = InterfaceExclusivaECAC()
    
    # Inicia o monitoramento anti-timeout em segundo plano
    threading.Thread(target=manter_ecac_logado, daemon=True).start()

    app.mainloop()
