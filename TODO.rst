=====
TO DO
=====

Cool things to work on:
-----------------------
* Mail attachments: https://github.com/ecederstrand/exchangelib/issues/15
* Notification subscriptions: https://msdn.microsoft.com/en-us/library/office/dn458790(v=exchg.150).aspx and https://msdn.microsoft.com/en-us/library/office/dn458791(v=exchg.150).aspx
* Password change for accounts: https://support.office.com/en-us/article/Change-password-in-Outlook-Web-App-50bb1309-6f53-4c24-8bfd-ed24ca9e872c
* SendItem service to send draft emails: https://msdn.microsoft.com/en-us/library/office/aa580238(v=exchg.150).aspx
* Support HTML body content. See http://stackoverflow.com/questions/20982851/how-to-get-the-email-body-in-html-and-text-from-exchange-using-ews-in-c
* Enforce SUBJECT_MAXLENGTH and LOCATION_MAXLENGTH (and other validations on item fields)
* Support lookups on ItemId and ChangeKey values: ``my_folder.get(item_id='xxx', changekey='yyy')` and
  ``my_folder.filter(item_id__in=['xxx', 'yyy'])`
