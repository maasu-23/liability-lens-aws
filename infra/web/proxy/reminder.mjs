// Lambda entry point that EventBridge Scheduler calls on the day: sends one reminder email.
// Logs only counts and outcomes, never the address or the text.
import { sendScheduled } from "./reminders.mjs";

export const handler = async (event) => {
  const result = await sendScheduled(event || {});
  console.log("reminder", result);
  return result;
};
