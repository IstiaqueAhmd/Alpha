import { sql } from "drizzle-orm";
import { integer, varchar, timestamp, pgTable } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { type getEventDownloaderProgresses } from "@/lib/api/eventDownloaderProgresses/queries";

import { nanoid, timestamps } from "@/lib/utils";

export const eventDownloaderProgresses = pgTable("event_downloader_progresses", {
  id: varchar("id", { length: 191 })
    .primaryKey()
    .$defaultFn(() => nanoid()),
  pagesProcessed: integer("pages_processed").notNull(),
  pages: integer("pages").notNull(),
  pageSize: integer("page_size").notNull(),
  providerName: varchar("provider_name", { length: 256 }).notNull(),

  createdAt: timestamp("created_at")
    .notNull()
    .default(sql`now()`),
  updatedAt: timestamp("updated_at")
    .notNull()
    .default(sql`now()`),
});

// Schema for eventDownloaderProgresses - used to validate API requests
const baseSchema = createSelectSchema(eventDownloaderProgresses).omit(timestamps);

export const insertEventDownloaderProgressSchema = createInsertSchema(eventDownloaderProgresses).omit(timestamps);
export const insertEventDownloaderProgressParams = baseSchema
  .extend({
    pagesProcessed: z.coerce.number(),
    pages: z.coerce.number(),
    pageSize: z.coerce.number(),
  })
  .omit({
    id: true,
  });

export const updateEventDownloaderProgressSchema = baseSchema;
export const updateEventDownloaderProgressParams = baseSchema.extend({
  pagesProcessed: z.coerce.number(),
  pages: z.coerce.number(),
  pageSize: z.coerce.number(),
});
export const eventDownloaderProgressIdSchema = baseSchema.pick({ id: true });

// Types for eventDownloaderProgresses - used to type API request params and within Components
export type EventDownloaderProgress = typeof eventDownloaderProgresses.$inferSelect;
export type NewEventDownloaderProgress = z.infer<typeof insertEventDownloaderProgressSchema>;
export type NewEventDownloaderProgressParams = z.infer<typeof insertEventDownloaderProgressParams>;
export type UpdateEventDownloaderProgressParams = z.infer<typeof updateEventDownloaderProgressParams>;
export type EventDownloaderProgressId = z.infer<typeof eventDownloaderProgressIdSchema>["id"];

// this type infers the return from getEventDownloaderProgresses() - meaning it will include any joins
export type CompleteEventDownloaderProgress = Awaited<
  ReturnType<typeof getEventDownloaderProgresses>
>["eventDownloaderProgresses"][number];
