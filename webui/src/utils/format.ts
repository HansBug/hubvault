import dayjs from "dayjs";
import relativeTime from "dayjs/plugin/relativeTime";

dayjs.extend(relativeTime);

export function formatBytes(value) {
  const size = Number(value || 0);
  if (size < 1024) {
    return size + " B";
  }
  const units = ["KB", "MB", "GB", "TB"];
  let current = size / 1024;
  let index = 0;
  while (current >= 1024 && index < units.length - 1) {
    current = current / 1024;
    index += 1;
  }
  return current.toFixed(1) + " " + units[index];
}

export function formatDateTime(value) {
  if (!value) {
    return "Unknown";
  }
  return dayjs(value).format("YYYY-MM-DD HH:mm:ss");
}

export function formatRelativeDate(value) {
  if (!value) {
    return "Unknown";
  }
  return dayjs(value).fromNow();
}

export function shortOid(value) {
  const text = String(value || "");
  return text.length > 10 ? text.slice(0, 10) : text;
}
