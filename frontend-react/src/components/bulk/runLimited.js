// Runs fn(item) for every item with at most `limit` in flight. Never rejects:
// each result is { item, ok, value } or { item, ok: false, error }, in the
// order of `items`.
export default async function runLimited(items, limit, fn) {
    const results = new Array(items.length);
    let next = 0;
    const worker = async () => {
        while (next < items.length) {
            const index = next;
            next += 1;
            const item = items[index];
            try {
                results[index] = { item, ok: true, value: await fn(item, index) };
            } catch (error) {
                results[index] = { item, ok: false, error };
            }
        }
    };
    const workers = [];
    for (let i = 0; i < Math.min(Math.max(limit, 1), items.length); i += 1) workers.push(worker());
    await Promise.all(workers);
    return results;
}
