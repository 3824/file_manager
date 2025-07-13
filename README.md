# File Manager

クロスプラットフォーム対応のPython製GUIファイルマネージャーアプリケーション

## 機能

- 左ペイン：フォルダーツリー表示
- 右ペイン：選択フォルダー内のファイル・フォルダー一覧表示
- Windows・Mac・Linux対応
- tkinterを使用したGUI（標準ライブラリなので追加インストール不要）

## 必要環境

- Python 3.7以上
- tkinter（Pythonに標準で含まれています）

## セットアップ手順

### 1. リポジトリのクローン
```bash
git clone <repository-url>
cd file_manager
```

### 2. 仮想環境の作成とアクティベート

#### Windows
```bash
python -m venv venv
venv\Scripts\activate
```

#### Mac/Linux
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. アプリケーションの実行
```bash
python file_manager.py
```

## 使用方法

1. アプリケーションを起動すると、左ペインにフォルダーツリーが表示されます
2. フォルダーをクリックして展開すると、サブフォルダーが表示されます
3. フォルダーを選択すると、右ペインにそのフォルダー内のファイル・フォルダー一覧が表示されます
4. ファイル一覧では以下の情報が表示されます：
   - ファイル/フォルダー名
   - タイプ（ファイルまたはフォルダー）
   - ファイルサイズ
   - 最終更新日時

## プラットフォーム固有の動作

### Windows
- すべてのドライブ（C:、D:等）がルートレベルに表示されます

### Mac/Linux
- ルートディレクトリ（/）とホームディレクトリが表示されます

## トラブルシューティング

### アクセス権限エラー
一部のシステムフォルダーにはアクセス権限がない場合があります。その場合は「アクセス権限がありません」と表示されます。

### tkinterが見つからない場合
```bash
# Ubuntu/Debian
sudo apt-get install python3-tk

# CentOS/RHEL
sudo yum install tkinter
# または
sudo dnf install python3-tkinter

# macOS（Homebrewを使用）
brew install python-tk
```

## 開発

### 共通コマンド
- `pytest tests/`: テストスイート実行
- `black .`: コードフォーマット適用

### コードスタイル
- 関数名：snake_case
- クラス名：PascalCase

