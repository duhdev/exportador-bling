@echo off
title Exportador Bling
cd /d "%~dp0"
where py >nul 2>nul && (py -3 servidor.py & goto fim)
where python >nul 2>nul && (python servidor.py & goto fim)
echo.
echo Python nao encontrado. Instale em https://www.python.org/downloads/
echo (marque "Add python.exe to PATH" na instalacao) e de dois cliques aqui de novo.
start https://www.python.org/downloads/
:fim
pause
