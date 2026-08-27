@echo off
setlocal
cd /d "%~dp0"
title ITH Bearing Temp - Telegram alert setup
echo ============================================================
echo   ITH Bearing Temp  -  Telegram alert setup
echo ============================================================
echo.
echo   STEP 1  In Telegram, search for   @BotFather   and press START.
echo           Send:   /newbot
echo           - it asks for a NAME      ->  ITH Bearing Temp
echo           - it asks for a USERNAME  ->  must end with "bot"
echo                                         e.g.  ith_bearing_temp_bot
echo           BotFather then replies with a TOKEN that looks like
echo               8123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
echo.
echo   STEP 2  Copy that token (select it, Ctrl+C).
echo           Notepad opens next. Paste the token between the quotes
echo           on the   "token": ""   line, then press Ctrl+S and close.
echo.
pause
notepad "%~dp0telegram_config.json"
echo.
echo   STEP 3  In Telegram, open your new bot and press START.
echo           (To alert a whole team instead: add the bot to a group
echo            and type any message in that group.)
echo.
pause
echo.
echo   Looking for your chat...
python "%~dp0telegram_alert.py" --setup
if errorlevel 1 goto fail
echo.
echo   Sending a test message...
python "%~dp0telegram_alert.py" --test
if errorlevel 1 goto fail
echo.
echo ============================================================
echo   Done. Check Telegram - the test message should be there.
echo   From now on you get an alert whenever any bearing hits 80 C,
echo   repeated every 15 minutes until it cools down.
echo ============================================================
goto end
:fail
echo.
echo ------------------------------------------------------------
echo   Not finished yet. Read the message just above:
echo     "no token"    -> the token was not saved into the file
echo     "no chat"     -> press START in the bot chat, then run again
echo ------------------------------------------------------------
:end
echo.
pause
