export function classNames(...classes) {
  return classes.filter(Boolean).join(' ');
}

export function formatDateTime(isoString) {
  if (!isoString) return 'N/A';
  try {
    const date = new Date(isoString);
    // Basic check for invalid date
    if (isNaN(date.getTime())) {
      return 'Invalid Date';
    }
    // Format to local date and time, e.g., "5/12/2025, 8:32:07 AM"
    return date.toLocaleString(undefined, { // Use browser's default locale
      year: 'numeric',
      month: 'numeric',
      day: 'numeric',
      hour: 'numeric',
      minute: '2-digit',
      second: '2-digit',
      hour12: true, // Use AM/PM
    });
  } catch (error) {
    console.error("Error formatting date:", isoString, error);
    return 'Invalid Date';
  }
}
