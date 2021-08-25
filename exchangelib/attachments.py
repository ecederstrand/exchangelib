import logging
import mimetypes
from io import BytesIO

from .fields import BooleanField, TextField, IntegerField, URIField, DateTimeField, EWSElementField, Base64Field, \
    ItemField, IdField, FieldPath
from .properties import EWSElement, EWSMeta
from .services import GetAttachment, CreateAttachment, DeleteAttachment

log = logging.getLogger(__name__)


class AttachmentId(EWSElement):
    """'id' and 'changekey' are UUIDs generated by Exchange.

    MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/attachmentid
    """

    ELEMENT_NAME = 'AttachmentId'

    ID_ATTR = 'Id'
    ROOT_ID_ATTR = 'RootItemId'
    ROOT_CHANGEKEY_ATTR = 'RootItemChangeKey'

    id = IdField(field_uri=ID_ATTR, is_required=True)
    root_id = IdField(field_uri=ROOT_ID_ATTR)
    root_changekey = IdField(field_uri=ROOT_CHANGEKEY_ATTR)


class Attachment(EWSElement, metaclass=EWSMeta):
    """Base class for FileAttachment and ItemAttachment."""

    attachment_id = EWSElementField(value_cls=AttachmentId)
    name = TextField(field_uri='Name')
    content_type = TextField(field_uri='ContentType')
    content_id = TextField(field_uri='ContentId')
    content_location = URIField(field_uri='ContentLocation')
    size = IntegerField(field_uri='Size', is_read_only=True)  # Attachment size in bytes
    last_modified_time = DateTimeField(field_uri='LastModifiedTime')
    is_inline = BooleanField(field_uri='IsInline')

    __slots__ = 'parent_item',

    def __init__(self, **kwargs):
        self.parent_item = kwargs.pop('parent_item', None)
        super().__init__(**kwargs)

    def clean(self, version=None):
        from .items import Item
        if self.parent_item is not None and not isinstance(self.parent_item, Item):
            raise ValueError("'parent_item' value %r must be an Item instance" % self.parent_item)
        if self.content_type is None and self.name is not None:
            self.content_type = mimetypes.guess_type(self.name)[0] or 'application/octet-stream'
        super().clean(version=version)

    def attach(self):
        # Adds this attachment to an item and updates the changekey of the parent item
        if self.attachment_id:
            raise ValueError('This attachment has already been created')
        if not self.parent_item or not self.parent_item.account:
            raise ValueError('Parent item %s must have an account' % self.parent_item)
        item = CreateAttachment(account=self.parent_item.account).get(parent_item=self.parent_item, items=[self])
        attachment_id = item.attachment_id
        if attachment_id.root_id != self.parent_item.id:
            raise ValueError("'root_id' vs. 'id' mismatch")
        if attachment_id.root_changekey == self.parent_item.changekey:
            raise ValueError('root_id changekey match')
        self.parent_item.changekey = attachment_id.root_changekey
        # EWS does not like receiving root_id and root_changekey on subsequent requests
        attachment_id.root_id = None
        attachment_id.root_changekey = None
        self.attachment_id = attachment_id

    def detach(self):
        # Deletes an attachment remotely and updates the changekey of the parent item
        if not self.attachment_id:
            raise ValueError('This attachment has not been created')
        if not self.parent_item or not self.parent_item.account:
            raise ValueError('Parent item %s must have an account' % self.parent_item)
        root_item_id = DeleteAttachment(account=self.parent_item.account).get(items=[self.attachment_id])
        if root_item_id.id != self.parent_item.id:
            raise ValueError("'root_item_id.id' mismatch")
        if root_item_id.changekey == self.parent_item.changekey:
            raise ValueError("'root_item_id.changekey' match")
        self.parent_item.changekey = root_item_id.changekey
        self.parent_item = None
        self.attachment_id = None

    def __hash__(self):
        if self.attachment_id:
            return hash(self.attachment_id)
        # Be careful to avoid recursion on the back-reference to the parent item
        return hash(tuple(getattr(self, f) for f in self._slots_keys if f != 'parent_item'))

    def __repr__(self):
        return self.__class__.__name__ + '(%s)' % ', '.join(
            '%s=%r' % (f.name, getattr(self, f.name)) for f in self.FIELDS if f.name not in ('_item', '_content')
        )


class FileAttachment(Attachment):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/fileattachment"""

    ELEMENT_NAME = 'FileAttachment'

    is_contact_photo = BooleanField(field_uri='IsContactPhoto')
    _content = Base64Field(field_uri='Content')

    __slots__ = '_fp',

    def __init__(self, **kwargs):
        kwargs['_content'] = kwargs.pop('content', None)
        super().__init__(**kwargs)
        self._fp = None

    @property
    def fp(self):
        # Return a file-like object for the content. This avoids creating multiple in-memory copies of the content.
        if self._fp is None:
            self._init_fp()
        return self._fp

    def _init_fp(self):
        # Create a file-like object for the attachment content. We try hard to reduce memory consumption so we never
        # store the full attachment content in-memory.
        if not self.parent_item or not self.parent_item.account:
            raise ValueError('%s must have an account' % self.__class__.__name__)
        self._fp = FileAttachmentIO(attachment=self)

    @property
    def content(self):
        """Return the attachment content. Stores a local copy of the content in case you want to upload the attachment
        again later.
        """
        if self.attachment_id is None:
            return self._content
        if self._content is not None:
            return self._content
        # We have an ID to the data but still haven't called GetAttachment to get the actual data. Do that now.
        with self.fp as fp:
            self._content = fp.read()
        return self._content

    @content.setter
    def content(self, value):
        """Replace the attachment content."""
        if not isinstance(value, bytes):
            raise ValueError("'value' %r must be a bytes object" % value)
        self._content = value

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS}
        kwargs['content'] = kwargs.pop('_content')
        cls._clear(elem)
        return cls(**kwargs)

    def to_xml(self, version):
        self._content = self.content  # Make sure content is available, to avoid ErrorRequiredPropertyMissing
        return super().to_xml(version=version)

    def __getstate__(self):
        # The fp does not need to be pickled
        state = {k: getattr(self, k) for k in self._slots_keys}
        del state['_fp']
        return state

    def __setstate__(self, state):
        # Restore the fp
        for k in self._slots_keys:
            setattr(self, k, state.get(k))
        self._fp = None


class ItemAttachment(Attachment):
    """MSDN: https://docs.microsoft.com/en-us/exchange/client-developer/web-service-reference/itemattachment"""

    ELEMENT_NAME = 'ItemAttachment'

    _item = ItemField(field_uri='Item')

    def __init__(self, **kwargs):
        kwargs['_item'] = kwargs.pop('item', None)
        super().__init__(**kwargs)

    @property
    def item(self):
        from .folders import BaseFolder
        if self.attachment_id is None:
            return self._item
        if self._item is not None:
            return self._item
        # We have an ID to the data but still haven't called GetAttachment to get the actual data. Do that now.
        if not self.parent_item or not self.parent_item.account:
            raise ValueError('%s must have an account' % self.__class__.__name__)
        additional_fields = {
            FieldPath(field=f) for f in BaseFolder.allowed_item_fields(version=self.parent_item.account.version)
        }
        attachment = GetAttachment(account=self.parent_item.account).get(
            items=[self.attachment_id], include_mime_content=True, body_type=None, filter_html_content=None,
            additional_fields=additional_fields,
        )
        self._item = attachment.item
        return self._item

    @item.setter
    def item(self, value):
        from .items import Item
        if not isinstance(value, Item):
            raise ValueError("'value' %r must be an Item object" % value)
        self._item = value

    @classmethod
    def from_xml(cls, elem, account):
        kwargs = {f.name: f.from_xml(elem=elem, account=account) for f in cls.FIELDS}
        kwargs['item'] = kwargs.pop('_item')
        cls._clear(elem)
        return cls(**kwargs)


class FileAttachmentIO(BytesIO):
    """A BytesIO where the stream of data comes from the GetAttachment service."""

    def __init__(self, *args, **kwargs):
        self._attachment = kwargs.pop('attachment')
        super().__init__(*args, **kwargs)

    def __enter__(self):
        self._stream = GetAttachment(account=self._attachment.parent_item.account).stream_file_content(
            attachment_id=self._attachment.attachment_id
        )
        self._overflow = b''
        return self

    def __exit__(self, *args, **kwargs):
        self._stream = None
        self._overflow = None

    def read(self, size=-1):
        if size < 0:
            # Return everything
            return b''.join(self._stream)
        # Return only 'size' bytes
        buffer = [self._overflow]
        read_size = len(self._overflow)
        while True:
            if read_size >= size:
                break
            try:
                next_chunk = next(self._stream)
            except StopIteration:
                break
            buffer.append(next_chunk)
            read_size += len(next_chunk)
        res = b''.join(buffer)
        self._overflow = res[size:]
        return res[:size]
