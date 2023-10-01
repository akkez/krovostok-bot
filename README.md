# Krovostok bot

https://t.me/KrovostokVoiceBot

```shell script
cp .env.example .env
# don't forget to set your variables in .env

docker build . --tag krovostok-bot 
docker run --restart=always -it -v $(pwd):/code krovostok-bot
```
