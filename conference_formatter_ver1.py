import streamlit as st
import google.generativeai as genai
import os
from datetime import datetime
import time

# ページ設定
st.set_page_config(
    page_title="学会情報整形ツール",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# スタイルの設定
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
        background-color: #4CAF50;
        color: white;
        font-weight: bold;
    }
    .output-box {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        font-family: monospace;
        white-space: pre-wrap;
    }
</style>
""", unsafe_allow_html=True)

# タイトル
st.title("🎓 学会情報整形ツール")
st.markdown("---")

# テンプレート定義（表示用）
TEMPLATE_DISPLAY = """
出力形式：
[blue][u][uri=URL] 学会名（開催日、開催場所）[/uri][/u][/blue]
筆頭演者名、共同演者名1、共同演者名2、...、演題名、演題番号、発表形式

例：
[blue][u][uri=https://www.credoinc.jp/jspe58/] 第58回日本小児内分泌学会学術集会（2025/10/30-11/1、千葉）[/uri][/u][/blue]
演者名、共同演者名、演題名、演題番号、発表形式
"""

# プロンプトテンプレート
SYSTEM_PROMPT = """
あなたは学会情報を整理する専門家です。
入力されたテキストから学会発表に関する情報を抽出し、指定されたフォーマットに沿って整形してください。

# 出力フォーマット
必ず以下の形式で3行で出力してください：

1行目: [blue][u][uri=URL]学会名（開催日、開催場所）[/uri][/u][/blue]
2行目: [b]演題名[/b]
3行目: 演者名（全員をカンマ区切りで列挙）

# 重要なルール
1. URLが不明な場合は [blue][u][uri=] のように空欄にする
2. 学会名の後に必ず（開催日、開催場所）を含める
3. 開催日の形式：
   - 国内学会：YYYY/MM/DD または YYYY/MM/DD-DD、場所
   - 海外学会：YYYY/MM/DD-DD, City, Country（・Hybridも記載があれば追加）
4. 演題名は必ず [b]演題名[/b] のように太字タグで囲む
5. 演者名は全員列挙し、カンマとスペースで区切る（筆頭演者から順に）
6. 不足情報は具体的に示す：
   - 日付不明→「日付」
   - 共同演者不明→「共同演者」
7. 演題番号、発表形式、セッション名などは出力に含めない（テンプレートにないため）
8. 学会名の略称と正式名称：
   - ASH = American Society of Hematology
   - ESPN = European Society for Paediatric Nephrology
   - EAACI = European Academy of Allergy and Clinical Immunology
   など、略称は正式名称または一般的な表記に展開

# 入力パターンの認識
- 「Session Name:」「Presentation Time:」→ 海外学会の採択通知
- 「登録番号：」「演題番号：」→ 国内学会
- 「Abstract Title:」「Authors:」→ 海外学会の抄録
- 「December 6-9, 2025」のような日付表記 → MM/DD-DD形式に変換

# 出力例

例1（国内学会）：
[blue][u][uri=https://www.micenavi.jp/endo2023/]第96回日本内分泌学会学術集会（2023/6/1-3、名古屋）[/uri][/u][/blue]
[b]Gタンパク共役型受容体101（GPR101）遺伝子変異を同定した複合型下垂体機能低下症の兄弟例[/b]
森川俊太郎、金子直哉、中山加奈子、菱村希、山口健史、佐々木大輔、上田泰弘、渡邊さやか、青柳勇人、中村明枝、真部淳

例2（海外学会 - ASH）：
[blue][u][uri=]67th ASH Annual Meeting and Exposition (2025/12/6-9, Orlando, Florida)[/uri][/u][/blue]
[b]Genetic landscape of pediatric myelodysplastic syndrome in Japan[/b]
Masataka Hasegawa, Kaito Mimura, Rintaro Ono, Dai Keino, Shin-Ichi Tsujimoto, Kiyotaka Isobe, Takao Deguchi, Hideto Iwafuchi, Hiroshi Moritake, Hironori Goto, Atsushi Manabe, Seishi Ogawa, Kenichi Yoshida, Daisuke Hasegawa

例3（情報不足）：
[blue][u][uri=]第67回日本小児血液・がん学会学術集会（日付、福岡国際会議場）[/uri][/u][/blue]
[b]小児骨髄異形成症候群のゲノム解析[/b]
長谷河昌孝、共同演者
"""

# API Key入力セクション
with st.sidebar:
    st.header("⚙️ 設定")
    api_key = st.text_input(
        "Gemini API Key",
        type="password",
        help="Google AI StudioからAPIキーを取得してください"
    )
    
    if api_key:
        st.success("✅ API Key設定済み")
    else:
        st.warning("⚠️ API Keyを入力してください")
    
    st.markdown("---")
    st.markdown("""
    ### 使い方
    1. Gemini API Keyを入力
    2. 左側に学会情報を貼り付け
    3. 「整形する」ボタンをクリック
    4. 右側の結果をコピー
    """)

# メインコンテンツ
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("📝 入力")
    input_text = st.text_area(
        "学会関連のメール・テキストを貼り付けてください",
        height=500,
        placeholder="""採択通知メール、登録完了メール、抄録などをコピー&ペーストしてください

国内学会の例：
第67回日本小児血液・がん学会学術集会
演題名：小児骨髄異形成症候群のゲノム解析
筆頭演者：長谷河 昌孝
共同演者：三村海渡、渡邉健太郎、岡田愛
日時：11月19日（水）11:10～12:00
会場：第4会場（福岡国際会議場）

海外学会の例：
Dear Dr. Hasegawa,
We are pleased to inform you that your abstract has been selected for poster presentation...
Session Name: 636. Myelodysplastic Syndromes
Session Date: December 8, 2025
Title: Genetic landscape of pediatric myelodysplastic syndrome in Japan
...""",
        key="input_area"
    )
    
    # ボタンを2つ並べる
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        process_button = st.button("🔄 整形する", type="primary", use_container_width=True)
    with btn_col2:
        clear_button = st.button("🗑️ クリア", use_container_width=True)

with col2:
    st.subheader("📤 出力")
    
    # 出力エリアのプレースホルダー
    output_placeholder = st.empty()
    
    # コピーボタンのプレースホルダー
    copy_placeholder = st.empty()

# クリアボタンの処理
if clear_button:
    st.rerun()

# 処理実行
if process_button:
    if not api_key:
        st.error("❌ API Keyを入力してください")
    elif not input_text:
        st.error("❌ 入力テキストを貼り付けてください")
    else:
        try:
            # ローディング表示
            with st.spinner("処理中... しばらくお待ちください"):
                # Gemini APIの設定
                genai.configure(api_key=api_key)
                model = genai.GenerativeModel('gemini-1.5-flash')
                
                # プロンプトの構築
                prompt = f"""
                {SYSTEM_PROMPT}
                
                # 入力テキスト
                {input_text}
                
                # 指示
                上記の入力テキストから学会情報を抽出し、以下の形式で3行で出力してください：
                
                1行目: [blue][u][uri=URL]学会名（日付、場所）[/uri][/u][/blue]
                2行目: [b]演題名[/b]
                3行目: 演者名（全員をカンマ区切り）
                
                - URLが不明の場合は[uri=]と空欄にする
                - 演題名は必ず[b][/b]タグで囲む
                - 不足情報は「日付」「共同演者」などの項目名を記載
                - 演題番号や発表形式の情報は出力に含めない（テンプレートにないため）
                """
                
                # APIコール
                response = model.generate_content(prompt)
                
                # 結果の表示
                if response and response.text:
                    # セッション状態に保存
                    st.session_state['output_text'] = response.text.strip()
                    
                    # 出力表示
                    with output_placeholder.container():
                        st.text_area(
                            "整形結果",
                            value=st.session_state['output_text'],
                            height=400,
                            key="output_area"
                        )
                    
                    # コピーボタン表示
                    with copy_placeholder.container():
                        if st.button("📋 結果をクリップボードにコピー", key="copy_btn"):
                            # JavaScriptでクリップボードにコピー
                            st.write(f"""
                            <script>
                            navigator.clipboard.writeText(`{st.session_state['output_text']}`);
                            </script>
                            """, unsafe_allow_html=True)
                            st.success("✅ クリップボードにコピーしました！")
                    
                    # 成功メッセージ
                    st.success("✅ 整形が完了しました")
                else:
                    st.error("❌ 処理結果が空です")
                    
        except Exception as e:
            error_message = str(e)
            if "quota" in error_message.lower():
                st.error("❌ エラー: API利用制限に達しました")
            elif "api" in error_message.lower():
                st.error("❌ エラー: APIキーが無効です")
            elif "network" in error_message.lower():
                st.error("❌ エラー: ネットワーク接続エラー")
            else:
                st.error(f"❌ エラー: {error_message}")

# 初期状態で出力エリアに説明を表示
if 'output_text' not in st.session_state:
    with output_placeholder.container():
        st.info("""
        ℹ️ ここに整形結果が表示されます
        
        **出力形式：**
        ```
        [blue][u][uri=URL]学会名（日付、場所）[/uri][/u][/blue]
        [b]演題名[/b]
        演者名（全員をカンマ区切り）
        ```
        
        **例：**
        ```
        [blue][u][uri=https://www.credoinc.jp/jspe58/]第58回日本小児内分泌学会学術集会（2025/10/30-11/1、千葉）[/uri][/u][/blue]
        [b]ハイブリッドクローズドループ療法が有効であったWolfram症候群の2例[/b]
        遠藤愛、金子直哉、菱村希、鈴木滋、中村明枝、森川俊太郎
        ```
        
        ※ 不足情報は項目名（「日付」「共同演者」など）で表示されます
        """)

# フッター
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #888;">
    <small>
    💡 ヒント: 複数の学会情報が混在している場合は、1つずつ処理してください<br>
    🔒 API Keyは保存されません。ページを更新すると再入力が必要です
    </small>
</div>
""", unsafe_allow_html=True)
