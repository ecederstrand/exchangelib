from . import move_item


class CopyItem(move_item.MoveItem):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/copyitem-operation"""
    SERVICE_NAME = 'CopyItem'
