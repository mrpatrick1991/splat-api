export function cloneObject(item: any) {
  return JSON.parse(JSON.stringify(item));
}