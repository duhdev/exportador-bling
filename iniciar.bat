@echo off
title Exportador Bling
cd /d "%~dp0"
rem O servidor sai com 3 depois de se atualizar pela tela e com 4 ao se atualizar na abertura: abre de novo.
set EXPORTADOR_REINICIA=1
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto sempython
set "ARGS="
:loop
%PY% servidor.py %ARGS%
if errorlevel 5 goto fim
if errorlevel 4 goto loop
if errorlevel 3 (set "ARGS=--sem-navegador" & goto loop)
goto fim
:sempython
echo.
echo Python nao encontrado. Instale em https://www.python.org/downloads/
echo (marque "Add python.exe to PATH" na instalacao) e de dois cliques aqui de novo.
start https://www.python.org/downloads/
:fim
pause
