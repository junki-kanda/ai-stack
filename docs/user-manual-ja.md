# AI-Stack 利用マニュアル（非エンジニア向け）

## 🎯 AI-Stackとは？

AI-Stackは、プログラミングタスクを自動化するAIアシスタントです。
あなたが「こんなプログラムを作って」とお願いすると、AIが自動的に：
1. 必要な情報を検索
2. コードを生成
3. テストを実行
4. 結果をSlackに通知

## 🚀 使い方（3ステップ）

### ステップ1: Slackで結果を受け取る準備

AI-Stackからの通知は、Slackの `#ai-stack-log` チャンネルに届きます。
このチャンネルに参加していることを確認してください。

### ステップ2: タスクをリクエストする

以下のコマンドをターミナル（Mac）またはコマンドプロンプト（Windows）にコピー＆ペーストしてください：

#### 例1: CSVファイルを処理するプログラム
```bash
curl -X POST https://ai-stack-junkikanda.fly.dev/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "task": "CSVファイルを読み込んで、売上合計を計算するPythonプログラムを作成",
    "keyword": "Python CSV pandas 売上集計"
  }'
```

#### 例2: Webスクレイピングツール
```bash
curl -X POST https://ai-stack-junkikanda.fly.dev/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "task": "ニュースサイトから最新記事のタイトルを取得するスクレイピングツール",
    "keyword": "Python BeautifulSoup requests スクレイピング"
  }'
```

#### 例3: データ可視化
```bash
curl -X POST https://ai-stack-junkikanda.fly.dev/trigger \
  -H "Content-Type: application/json" \
  -d '{
    "task": "月別売上データをグラフで可視化するプログラム",
    "keyword": "Python matplotlib グラフ 可視化"
  }'
```

### ステップ3: Slackで結果を確認

5〜10分後、Slackに以下のような通知が届きます：

**成功した場合:**
```
✅ AI-Stack Job Success
Job completed successfully
{
  "task": "CSVファイルを読み込んで...",
  "code": "生成されたコード",
  "test_results": "テスト結果"
}
```

**失敗した場合:**
```
❌ AI-Stack Job Failed
Job failed after 3 retries
{
  "task": "...",
  "error": "エラーの詳細"
}
```

## 📊 現在の処理状況を確認

現在実行中のタスクや過去の結果を確認できます：

```bash
# 現在の状態を確認
curl https://ai-stack-junkikanda.fly.dev/status

# システムの稼働状況を確認
curl https://ai-stack-junkikanda.fly.dev/health
```

## 💰 コスト情報の確認

AI利用にかかったコストを確認できます：

```bash
curl https://ai-stack-junkikanda.fly.dev/cost
```

## ❓ よくある質問

### Q: どんなタスクをお願いできますか？
A: Pythonで実装可能なプログラミングタスクなら何でもOKです。例：
- データ処理（CSV、Excel、JSON）
- Web API連携
- ファイル操作
- 簡単な機械学習
- Webスクレイピング

### Q: 結果のコードはどこで見れますか？
A: Slackの通知内に含まれています。また、生成されたコードはGitHubにも保存されます。

### Q: エラーが出た場合は？
A: AI-Stackは自動的に3回までリトライします。それでも失敗した場合は、エンジニアチームが確認します。

### Q: 処理にどれくらい時間がかかりますか？
A: 通常5〜10分です。複雑なタスクの場合は15分程度かかることもあります。

## 🆘 サポート

問題が発生した場合は、以下にご連絡ください：
- Slack: `#ai-stack-support`
- または、エンジニアチームまで直接お声がけください

## 📝 タスクの書き方のコツ

良い例：
- ✅ 「CSVファイルから重複を削除して、結果を新しいファイルに保存」
- ✅ 「APIから天気データを取得して、1週間の予報をテーブル形式で表示」

避けた方が良い例：
- ❌ 「プログラムを作って」（具体性がない）
- ❌ 「AIで何かすごいことをして」（曖昧すぎる）

---

最終更新日: 2025年5月28日