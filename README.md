eneos-denki
============================

Lambdaの定期実行にてエネオスでんきの電力使用状況をメール通知する。

## 事前準備

### Lambda Layers用データ作成

コンパイルが走るのでpygalはAmazon Linux上でつくる。

```
docker run -it --rm -v $PWD/layers:/layers --entrypoint="" lambci/lambda:python3.7 /bin/bash
cd /layers

mkdir python
pip install -t ./python cairosvg pygal
exit
cd layers
zip -r pygal.zip python
cd ..
rm -rf layers

mkdir python
python3 -m pip install -t ./python selenium
zip -r selenium.zip python

curl -SL https://github.com/adieuadieu/serverless-chrome/releases/download/v1.0.0-41/stable-headless-chromium-amazonlinux-2017-03.zip > headless-chromium.zip
unzip headless-chromium.zip && rm headless-chromium.zip
curl -SL https://chromedriver.storage.googleapis.com/2.37/chromedriver_linux64.zip > chromedriver.zip
unzip chromedriver.zip && rm chromedriver.zip
zip headless-chromium.zip chromedriver headless-chromium
# 最新バージョンだと動かない模様、またpython3.8だと動かない。(amazonlinuxのバージョンが上がってるため)
```

* Lambda -> レイヤーの作成
    - 名前
        - headless-chromium, selenium
    - アップロード
        - headless-chromium.zip, selenium.zip
    - ランタイム
        - Python 3.6, 3.7

* Lambda -> レイヤーの作成
    - 名前
        - pygal
    - アップロード
        - pygal.zip
    - ランタイム
        - Python 3.7

### AWS SES

AWSのSESにて送信元と送信先をVerifyしておく。

## AWS Lambda 関数作成

* Lambda -> 関数の作成 -> 一から作成
    - 関数名
        - eneos-denki
    - ランタイム
        - Python 3.7
    - 実行ロール
        - eneos-denki
            - AmazonSESFullAccess などをアタッチしたもの
    - ハンドラ
        - main.main
    - タイムアウト
        - 3分
    - メモリ
        - 512MB
    - リトライ
        - 0回
    - 環境変数
        - ENEOS_DENKI_SES_REGION
        - ENEOS_DENKI_MAIL_FROM
        - ENEOS_DENKI_MAIL_TO
        - ENEOS_DENKI_USER_ID
        - ENEOS_DENKI_USER_PASSWORD
    - トリガーを追加
        - CloudWatch Events
            - 新規ルールの作成
            - ルール名: 8am-every-day
            - cron(0 23 ? * * *)
    - レイヤーの追加
        - headless-chromium, selenium, pygal
    - このリポジトリのzipをアップロード
        - そのうちgithubと連動させてもいい(serverlessでも。)


### ローカル実行環境も構築(Macの場合)

```
pip install selenium
brew tap homebrew/cask
brew cask install chromedriver
```

環境変数にＥＮＥＯＳでんきのid/passなどを追加。

```
echo export ENEOS_DENKI_USER_ID=hogehoge >> ~/.bash_profile
echo export ENEOS_DENKI_USER_PASSWORD=hogehoge >> ~/.bash_profile
echo export ENEOS_DENKI_AWS_PROFILE=***** >> ~/.bash_profile # デフォルトプロファイルじゃない場合のみ
echo export ENEOS_DENKI_SES_REGION=us-west-2 >> ~/.bash_profile
echo export ENEOS_DENKI_MAIL_FROM=***@gmail.com >> ~/.bash_profile
echo export ENEOS_DENKI_MAIL_TO=***@gmail.com,***@gmail.com >> ~/.bash_profile
source ~/.bash_profile
```

## 連絡先

* [twitter: @m_cre](https://twitter.com/m_cre)

## License

* MIT
  + see LICENSE