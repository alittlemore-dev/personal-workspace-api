from dataclasses import dataclass
from functools import partial

from core.knowledge.files.clients import (
    KnowledgeFileObjectCleaner,
    KnowledgeFileRollbackRegistrar,
)
from infra.post_commit_actions import RollbackActions


@dataclass(kw_only=True, slots=True, frozen=True)
class RequestKnowledgeFileRollbackRegistrar(KnowledgeFileRollbackRegistrar):
    object_cleaner: KnowledgeFileObjectCleaner
    rollback_actions: RollbackActions

    def register_new_object(self, *, object_name: str) -> None:
        self.rollback_actions.add(
            action=partial(
                self.object_cleaner.cleanup_objects,
                object_names=(object_name,),
            ),
        )
