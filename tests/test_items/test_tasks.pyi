from .test_basics import CommonItemTest as CommonItemTest
from exchangelib.folders import Tasks
from exchangelib.items import Task

class TasksTest(CommonItemTest):
    TEST_FOLDER: str
    FOLDER_CLASS = Tasks
    ITEM_CLASS = Task
    def test_task_validation(self) -> None: ...
    def test_complete(self) -> None: ...
    def test_recurring_item(self) -> None: ...
