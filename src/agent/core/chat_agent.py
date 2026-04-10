"""ReAct Chat Agent: Think→Act→Observe ループで確実にツールを実行する。

Claude Code のように:
- 1回のやりとりで1つのツールを確実に実行
- 結果を確認してから次のステップに進む
- LLM が「実行したフリ」で嘘をつくことを防ぐ

フロー:
  user: "デスクトップにフォルダ作って Docker 環境準備して"
    ↓
  [Think] "まずフォルダを作る"
  [Act]   shell_runner: mkdir /path/to/my-app
  [Observe] (成功)
    ↓
  [Think] "次に main.py を書く"
  [Act]   file_ops: write main.py
  [Observe] (成功)
    ↓
  ... 1つずつ繰り返し ...
    ↓
  [Think] "全部完了した。結果を報告する"
  [Response] "環境を構築しました。"
"""
from __future__ import annotations

import json
from collections.abc import AsyncIterator

from agent.llm.base import BaseLLM, Message
from agent.tools.base import BaseTool


_REACT_SYSTEM = """\
あなたはローカルで動作するAIアシスタントです。ファイル操作、コマンド実行、コード実行などが可能です。

## 利用可能なツール
{tool_descriptions}

## ツール呼び出しの具体例 (args の形式を厳守すること)

ファイルを読む:
{{"tool": "file_ops", "args": {{"action": "read", "path": "/tmp/test.txt"}}, "thought": "ファイルの中身を読む"}}

ファイルに書き込む:
{{"tool": "file_ops", "args": {{"action": "write", "path": "/tmp/test.txt", "content": "Hello World"}}, "thought": "ファイルに書き込む"}}

ファイルを検索 (glob):
{{"tool": "file_ops", "args": {{"action": "glob", "pattern": "/tmp/*.txt"}}, "thought": "txtファイルを検索"}}

シェルコマンド:
{{"tool": "shell_runner", "args": {{"command": "ls -la /tmp"}}, "thought": "ディレクトリの中身を確認"}}

Python コード実行:
{{"tool": "code_executor", "args": {{"code": "print(1+1)"}}, "thought": "計算を実行"}}

Python ファイル実行:
{{"tool": "code_executor", "args": {{"path": "/tmp/script.py"}}, "thought": "スクリプトを実行"}}

注意: file_ops には operation, mode, read_file 等の引数はない。必ず action="read"|"write"|"glob" を使う。

## 応答ルール

ユーザーの要求に対して、以下のいずれかの形式で応答してください:

### ツールを1つ実行する場合:
上記の具体例の args 形式を厳守し、JSONのみを返してください。説明文は禁止。
{{"tool": "<ツール名>", "args": {{...}}, "thought": "<なぜこのツールを使うか>"}}

### ツール不要で回答できる場合:
通常の自然文で応答してください。JSONは含めないでください。

ツールを使わない例:
- 「1+1は？」→ 暗算で答えられるのでツール不要、「2です」と回答
- 「chmodコマンドとは？」→ 知識で答えられるのでツール不要
- 「Pythonのvenvの作り方は？」→ 知識で答えられるのでツール不要
- 一般的な質問、概念の説明、コードの書き方の説明はツール不要

## 重要なルール
- 1回の応答で実行するツールは1つだけ
- 「実行しました」「作成しました」と嘘をつかない。ツールを使っていないなら実行していない
- 知らないことは知らないと答える
- コードレビューで問題がなければ「問題ありません」と正直に答える
- ファイルを作る時は必ず file_ops ツールを使う。コードブロックで見せるだけでは作成していない
- コマンドを実行する時は必ず shell_runner ツールを使う
- 「カレントディレクトリはどこ」「今の日時」等の実行環境の情報を聞かれたら、知識で答えず必ず shell_runner で pwd や date を実行して確認する
- ファイルの中身を聞かれたら、必ず file_ops の read で実際に読んで、その内容を回答に含める

## 安全性ルール (厳守)
- rm -rf, sudo, /etc/passwd の表示、ホームディレクトリの重要ファイル (.bashrc, .ssh 等) の削除・変更は絶対に実行しない
- 上記の危険な要求を受けたら、ツールを呼ばず「セキュリティ上の理由で実行できません」と回答する
- /tmp 配下と明示されたプロジェクトディレクトリ以外へのファイル書き込み・削除は拒否する

## 環境情報
- この環境は WSL2 (Ubuntu) 上で動作している
- Windows のパスは /mnt/c/... に変換して使う
  例: C:\\Users\\aoish → /mnt/c/Users/aoish
  例: C:\\Users\\aoish\\OneDrive\\デスクトップ → /mnt/c/Users/aoish/OneDrive/デスクトップ
- シェルコマンドは Linux (bash) コマンドを使う
- mkdir -p でディレクトリを再帰的に作成する
- ツール実行が失敗したら、原因を分析して別の方法を自分で試す。ユーザーに聞く前に少なくとも2回は自分で試行する
- file_ops の write でファイルに日本語や特殊文字を書く場合、content にそのまま渡す (エスケープ不要)
"""


class ChatAgent:
    """ReAct パターンの Chat Agent。Think→Act→Observe ループ。"""

    def __init__(
        self,
        llm: BaseLLM,
        tools: list[BaseTool],
        system: str = "",
        max_steps: int = 15,
    ) -> None:
        self.llm = llm
        self.tools = {t.name: t for t in tools}
        self.max_steps = max_steps

        tool_desc = "\n".join(
            f"- {t.name}: {t.description}" for t in tools
        )
        sys_prompt = system or _REACT_SYSTEM.format(tool_descriptions=tool_desc)
        self.history: list[Message] = [Message(role="system", content=sys_prompt)]

    async def send(self, user_input: str) -> str:
        """同期版: 全ステップ実行後に最終応答を返す。"""
        result_chunks = []
        async for chunk in self.send_stream(user_input):
            result_chunks.append(chunk)
        return "".join(result_chunks)

    async def send_stream(self, user_input: str) -> AsyncIterator[str]:
        """ストリーミング版: 各ステップの途中経過をリアルタイムで返す。"""
        self.history.append(Message(role="user", content=user_input))

        for step in range(self.max_steps):
            # Think: LLM に次のアクションを判断させる
            response = await self.llm.generate(
                self.history, options={"temperature": 0.3}
            )

            # ツール呼び出し意図を検出
            tool_call = self._extract_tool_call(response)

            if tool_call is None:
                # ツール不要 = 最終応答
                self.history.append(Message(role="assistant", content=response))
                yield response
                return

            tool_name = tool_call["tool"]
            tool_args = tool_call["args"]
            thought = tool_call.get("thought", "")

            # ストリーミングで途中経過を表示
            if thought:
                yield f"💭 {thought}\n"
            yield f"🔧 {tool_name} を実行中...\n"

            # Act: 1つだけツールを実行
            tool = self.tools.get(tool_name)
            if tool is None:
                error_msg = f"❌ 不明なツール: {tool_name}\n"
                yield error_msg
                self.history.append(
                    Message(role="assistant", content=f"[tool call] {tool_name}({tool_args})")
                )
                self.history.append(
                    Message(role="user", content=f"[tool error] ツール '{tool_name}' は存在しません。利用可能: {', '.join(self.tools.keys())}")
                )
                continue

            try:
                result = await tool.execute(**tool_args)
            except Exception as e:
                result_text = f"❌ 実行エラー: {type(e).__name__}: {e}\n"
                yield result_text
                self.history.append(
                    Message(role="assistant", content=f"[tool call] {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")
                )
                self.history.append(
                    Message(role="user", content=f"[tool error] {result_text}")
                )
                continue

            # Observe: 結果を表示して履歴に追加
            if result.ok:
                observe_text = result.output[:2000] if result.output else "(成功、出力なし)"
                yield f"✅ 完了\n"
                if result.output:
                    yield f"```\n{result.output[:1000]}\n```\n"
            else:
                observe_text = f"エラー: {result.error[:1000]}"
                yield f"❌ {observe_text}\n"

            # 履歴に追加 (LLM は次のステップでこの結果を見る)
            self.history.append(
                Message(role="assistant", content=f"[tool call] {tool_name}({json.dumps(tool_args, ensure_ascii=False)})")
            )
            self.history.append(
                Message(
                    role="user",
                    content=f"[tool result] ok={result.ok}\n{observe_text}\n\n上記のツール実行結果を踏まえて、次のステップに進んでください。すべて完了したら、ツール結果の内容を含めてユーザーに報告してください。ファイルの中身を読んだ場合は、その内容をそのまま回答に含めてください。",
                )
            )

        # max_steps 到達
        yield "\n⚠️ 最大ステップ数に到達しました。ここまでの結果を確認してください。\n"

    def _extract_tool_call(self, response: str) -> dict | None:
        """LLM 応答からツール呼び出し意図を抽出。

        対応パターン:
        1. {"tool": ..., "args": ...}
        2. ```json\n{"tool": ...}\n```
        3. {"tool":...}\n{"tool":...}  → 最初の1つだけ取る
        """
        import re

        # コードフェンス除去
        cleaned = re.sub(r"```(?:json)?\s*", "", response)
        cleaned = cleaned.replace("```", "")

        # 最初の { から対応する } を brace-balancing で探す
        start = cleaned.find("{")
        if start == -1:
            return None

        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(cleaned)):
            c = cleaned[i]
            if esc:
                esc = False
                continue
            if c == "\\":
                esc = True
                continue
            if c == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    candidate = cleaned[start : i + 1]
                    try:
                        data = json.loads(candidate)
                        if "tool" in data and "args" in data:
                            tool_name = data["tool"]
                            if tool_name in self.tools:
                                return data
                    except json.JSONDecodeError:
                        pass
                    break

        return None
