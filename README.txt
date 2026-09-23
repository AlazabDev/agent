هذه الملفات التي أنشأناها/عدّلناها اليوم، محفوظة بنفس مسارها النسبي كما في مستودع
AlazabDev/agent (فرع version-16). لتطبيقها على سيرفركم، فك الضغط داخل جذر تطبيق
الـ agent مباشرة، أي داخل:

    ~/frappe-bench/apps/agent/

بحيث تنسخ الملفات إلى:
    ~/frappe-bench/apps/agent/agent/ai_control/bench_dev.py   (ملف جديد)
    ~/frappe-bench/apps/agent/agent/bench_dev_routes.py       (ملف جديد)
    ~/frappe-bench/apps/agent/agent/web.py                    (استبدال -- خذ نسخة احتياطية أولاً)
    ~/frappe-bench/apps/agent/scripts/register_agent.py       (ملف جديد)
    ~/frappe-bench/apps/agent/scripts/agents/_template.json   (ملف جديد)
    ~/frappe-bench/apps/agent/scripts/agents/az-agent-codex.json (ملف جديد)

تنبيه مهم: web.py هنا هو نسخة معدَّلة من نسخة فرع version-16 الرسمي، وليس من نسخة
سيرفركم الحالية (التي تبيّن أنها مختلفة/غير محدّثة). لا تستبدل به web.py الحالي
عندكم مباشرة قبل أن نراجع ناتج أمر git status الذي طلبته في الرسالة السابقة --
قد يكون عندكم تعديلات محلية أخرى غير موجودة في version-16 ستُفقد لو استُبدل الملف
كاملاً بلا مقارنة أولاً.
