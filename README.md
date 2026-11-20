# Restaurant Order Management

واجهة Tkinter لإدارة العملاء والمنيو والطلبات باستخدام SQL Server على Windows.

## التشغيل لأول مرة

1. ثبّت Python مع Tkinter، وSQL Server Database Engine، وSSMS، وMicrosoft ODBC Driver 18 for SQL Server.
2. اتصل بالسيرفر المحلي في SSMS باستخدام Windows Authentication. افتح setup.sql واضغط Execute مرة واحدة. السكريبت ينشئ RESTAURANT ببيانات تجريبية ويتوقف لو فيها جداول بالفعل.
3. الواجهة تستخدم localhost. لو اسم السيرفر في SSMS هو localhost\SQLEXPRESS، غيّر SERVER=localhost في ملف Python إلى SERVER=localhost\\SQLEXPRESS (شرطتان عكسيتان داخل نص Python).
4. افتح PowerShell داخل فولدر المشروع ونفّذ:

```powershell
py -m pip install -r requirements.txt
py restaurant_crud.py
```

## تجربة طلب

اختار عميل ثم FRENCH FRIES بكمية 2. اضغط Add to Order. الإجمالي المتوقع 90 جنيه. اضغط Save Order وراجع رقم الطلب في Order History وOrder details. كل جهاز له بيانات محلية مستقلة. إجمالي الطلب يُحسب عند الحفظ الأول، وتعديل التفاصيل لاحقًا يحتاج مراجعة الإجمالي المخزن.
