@echo off
setlocal
cd /d "%~dp0"

rem Verifica se o .venv e valido neste PC; se nao for, apaga para recriar
rem (ex.: .venv copiado de outro computador, ou apagado pela metade)
call :venv_ok
if errorlevel 1 if exist ".venv" (
    echo Ambiente Python invalido neste PC, recriando...
    rmdir /s /q ".venv" >nul 2>&1
    if exist ".venv" (
        echo.
        echo Nao foi possivel apagar a pasta .venv - algum arquivo esta em uso.
        echo Feche o easy4idle, apague a pasta ".venv" manualmente e rode este arquivo de novo.
        pause
        exit /b 1
    )
)

if not exist ".venv" (
    where python >nul 2>&1
    if errorlevel 1 (
        echo Python nao encontrado. Instale o Python 3.12 em https://www.python.org/downloads/
        echo e marque a opcao "Add python.exe to PATH" durante a instalacao.
        pause
        exit /b 1
    )
    echo Criando ambiente Python...
    python -m venv .venv
    call :venv_ok
    if errorlevel 1 (
        echo.
        echo Falha ao criar o ambiente Python. Verifique se o Python 3.12 esta instalado
        echo pelo site python.org - nao pela Microsoft Store.
        pause
        exit /b 1
    )
)

rem Instala/atualiza as dependencias quando o requirements.txt muda
fc /b requirements.txt ".venv\requirements.instalado" >nul 2>&1
if errorlevel 1 (
    echo Instalando dependencias...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo Falha ao instalar as dependencias. Verifique a internet e rode este arquivo de novo.
        pause
        exit /b 1
    )
    copy /y requirements.txt ".venv\requirements.instalado" >nul
)

start "" ".venv\Scripts\pythonw.exe" easy4idle.py
exit /b 0

:venv_ok
if not exist ".venv\pyvenv.cfg" exit /b 1
if not exist ".venv\Scripts\pythonw.exe" exit /b 1
".venv\Scripts\python.exe" -c "import sys" >nul 2>&1
exit /b %errorlevel%
