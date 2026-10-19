import sys
sys.path.insert(0, 'src')
from pathlib import Path
from modules.codegen.diff_applier import DiffApplier

SERVICES = Path(r'C:\Users\lnellutl\Downloads\aie-forge-main\services')
f = SERVICES / 'account-service/src/index.js'
original_bytes = f.read_bytes()
original_text = original_bytes.replace(b'\r\n', b'\n').decode('utf-8')
original_lines = original_text.splitlines()

# Real AI diff (simplified console.log to avoid escape issues in test)
diff = """--- a/account-service/src/index.js
+++ b/account-service/src/index.js
@@ -10,11 +10,18 @@
 app.use(cors());
 app.use(express.json());
 
-// Request logging
+// Request and response logging
 app.use((req, res, next) => {
-  console.log(`[ts] method path`);
+  const startTime = Date.now();
   next();
 });
+
 // Health check
 app.get('/health', (req, res) => {"""

applier = DiffApplier.__new__(DiffApplier)
applier._services_root = SERVICES

try:
    result = applier._apply_hunks(original_lines, diff)
    print(f'SUCCESS! {len(original_lines)} -> {len(result)} lines')
    print('Lines 9-22:')
    for i, l in enumerate(result[8:22], 9):
        print(f'  {i}: {l}')
except Exception as e:
    import traceback
    print(f'FAILED: {e}')
    traceback.print_exc()
