const DB_NAME = "video_auto_cut_local_cache";
const DB_VERSION = 1;
const STORE_NAME = "job_source_videos";
const EXPIRE_MS = 7 * 24 * 60 * 60 * 1000;

type CachedVideoRecord = {
  jobId: string;
  name: string;
  type: string;
  lastModified: number;
  file: Blob;
  updatedAt: number;
};

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof window === "undefined" || !window.indexedDB) {
      reject(new Error("indexeddb_unavailable"));
      return;
    }
    const req = window.indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: "jobId" });
        store.createIndex("updatedAt", "updatedAt", { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error("indexeddb_open_failed"));
  });
}

function runTx<T>(
  db: IDBDatabase,
  mode: IDBTransactionMode,
  fn: (store: IDBObjectStore, resolve: (value: T) => void, reject: (reason?: unknown) => void) => void
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, mode);
    const store = tx.objectStore(STORE_NAME);
    fn(store, resolve, reject);
    tx.onerror = () => reject(tx.error || new Error("indexeddb_tx_failed"));
  });
}

async function pruneExpired(db: IDBDatabase): Promise<void> {
  const now = Date.now();
  await runTx<void>(db, "readwrite", (store, resolve, reject) => {
    const req = store.openCursor();
    req.onsuccess = () => {
      const cursor = req.result;
      if (!cursor) {
        resolve();
        return;
      }
      const record = cursor.value as CachedVideoRecord;
      if (!record || typeof record.updatedAt !== "number" || now - record.updatedAt > EXPIRE_MS) {
        cursor.delete();
      }
      cursor.continue();
    };
    req.onerror = () => reject(req.error || new Error("indexeddb_prune_failed"));
  });
}

export async function saveCachedJobSourceVideo(jobId: string, file: File): Promise<void> {
  const db = await openDb();
  try {
    await runTx<void>(db, "readwrite", (store, resolve, reject) => {
      const record: CachedVideoRecord = {
        jobId,
        name: file.name || "source.mp4",
        type: file.type || "video/mp4",
        lastModified: Number.isFinite(file.lastModified) ? file.lastModified : Date.now(),
        file,
        updatedAt: Date.now(),
      };
      const req = store.put(record);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error || new Error("indexeddb_put_failed"));
    });
    await pruneExpired(db);
  } finally {
    db.close();
  }
}

export async function loadCachedJobSourceVideo(jobId: string): Promise<File | null> {
  const db = await openDb();
  try {
    const record = await runTx<CachedVideoRecord | null>(db, "readonly", (store, resolve, reject) => {
      const req = store.get(jobId);
      req.onsuccess = () => resolve((req.result as CachedVideoRecord | undefined) || null);
      req.onerror = () => reject(req.error || new Error("indexeddb_get_failed"));
    });
    if (!record) return null;
    if (Date.now() - record.updatedAt > EXPIRE_MS) {
      await removeCachedJobSourceVideo(jobId);
      return null;
    }
    return new File([record.file], record.name || "source.mp4", {
      type: record.type || "video/mp4",
      lastModified: record.lastModified || Date.now(),
    });
  } finally {
    db.close();
  }
}

export async function removeCachedJobSourceVideo(jobId: string): Promise<void> {
  const db = await openDb();
  try {
    await runTx<void>(db, "readwrite", (store, resolve, reject) => {
      const req = store.delete(jobId);
      req.onsuccess = () => resolve();
      req.onerror = () => reject(req.error || new Error("indexeddb_delete_failed"));
    });
  } finally {
    db.close();
  }
}

