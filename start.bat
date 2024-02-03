@echo off
cls

echo Have you installed the modules? (y/n)
set /p response=

if /i "%response%"=="y" (
    echo Running the main.py script
    python main.py
) else if /i "%response%"=="n" (
    echo Installing modules...
    call install.bat
    echo Modules installed successfully! Running the main.py script
    start python main.py
) else (
    echo Invalid response. Please answer with 'y' or 'n'.
)

pause
