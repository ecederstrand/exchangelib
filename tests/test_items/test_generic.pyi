from ..common import get_random_string as get_random_string, mock_version as mock_version
from .test_basics import CommonItemTest as CommonItemTest
from exchangelib.folders import Folder
from exchangelib.items import Item

class GenericItemTest(CommonItemTest):
    FOLDER_CLASS = Folder
    ITEM_CLASS = Item
    def test_validation(self) -> None: ...
    def test_invalid_direct_args(self) -> None: ...
    def test_invalid_createitem_args(self) -> None: ...
    def test_invalid_deleteitem_args(self) -> None: ...
    def test_invalid_updateitem_args(self) -> None: ...
    def test_invalid_finditem_args(self) -> None: ...
    def test_invalid_findpeople_args(self) -> None: ...
    def test_unsupported_fields(self) -> None: ...
    def test_order_by(self) -> None: ...
    def test_order_by_on_multiple_fields(self) -> None: ...
    def test_order_by_with_empty_values(self) -> None: ...
    def test_order_by_on_list_field(self) -> None: ...
    def test_finditems(self) -> None: ...
    def test_filter_with_querystring(self) -> None: ...
    def test_complex_fields(self) -> None: ...
    def test_text_body(self) -> None: ...
    def test_only_fields(self) -> None: ...
    def test_export_and_upload(self): ...
    def test_export_with_error(self) -> None: ...
    def test_archive(self) -> None: ...
    def test_item_attachments(self): ...
