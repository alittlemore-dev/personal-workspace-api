from functools import partial

from core.knowledge.files.clients import KnowledgeFileObjectCleaner
from infra.post_commit_actions import PostCommitActions


def register_knowledge_object_cleanup(
    *,
    object_names: tuple[str, ...],
    object_cleaner: KnowledgeFileObjectCleaner,
    post_commit_actions: PostCommitActions,
) -> None:
    if not object_names:
        return
    post_commit_actions.add(
        action=partial(
            object_cleaner.cleanup_objects,
            object_names=object_names,
        ),
    )
