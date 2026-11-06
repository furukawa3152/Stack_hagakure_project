"""TaskAgent。Grok Bot にはまだ接続しない。"""

from __future__ import annotations


class TaskAgent:
    async def submit_task(self, text: str) -> str:
        raise NotImplementedError

    async def get_status(self, task_id: str) -> str:
        raise NotImplementedError

    async def cancel_task(self, task_id: str) -> None:
        raise NotImplementedError


class GrokBotTaskAgent(TaskAgent):
    """Mac 上の gbot 経路を、後からこのクラスの中だけに閉じ込める。"""

    async def submit_task(self, text: str) -> str:
        del text
        raise NotImplementedError(
            "Grok Bot への引き渡しは Phase 5 です。先に Mac 上で gbot の単独疎通を確認します。"
        )

    async def get_status(self, task_id: str) -> str:
        del task_id
        raise NotImplementedError("Grok Bot の状態取得は未実装です。")

    async def cancel_task(self, task_id: str) -> None:
        del task_id
        raise NotImplementedError("Grok Bot の取消は未実装です。")
