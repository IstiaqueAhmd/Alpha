import { sql } from "drizzle-orm";
import { varchar, boolean, timestamp, pgTable } from "drizzle-orm/pg-core";
import { createInsertSchema, createSelectSchema } from "drizzle-zod";
import { z } from "zod";

import { type getPerformerScorerProgresses } from "@/lib/api/performerScorerProgresses/queries";

import { nanoid, timestamps } from "@/lib/utils";


export const performerScorerProgresses = pgTable('performer_scorer_progresses', {
  id: varchar("id", { length: 191 }).primaryKey().$defaultFn(() => nanoid()),
  lastProcessedPerformerId: varchar("last_processed_performer_id", { length: 256 }).notNull(),
  completed: boolean("completed").notNull(),
  
  createdAt: timestamp("created_at")
    .notNull()
    .default(sql`now()`),
  updatedAt: timestamp("updated_at")
    .notNull()
    .default(sql`now()`),

});


// Schema for performerScorerProgresses - used to validate API requests
const baseSchema = createSelectSchema(performerScorerProgresses).omit(timestamps)

export const insertPerformerScorerProgressSchema = createInsertSchema(performerScorerProgresses).omit(timestamps);
export const insertPerformerScorerProgressParams = baseSchema.extend({
  completed: z.coerce.boolean()
}).omit({ 
  id: true
});

export const updatePerformerScorerProgressSchema = baseSchema;
export const updatePerformerScorerProgressParams = baseSchema.extend({
  completed: z.coerce.boolean()
})
export const performerScorerProgressIdSchema = baseSchema.pick({ id: true });

// Types for performerScorerProgresses - used to type API request params and within Components
export type PerformerScorerProgress = typeof performerScorerProgresses.$inferSelect;
export type NewPerformerScorerProgress = z.infer<typeof insertPerformerScorerProgressSchema>;
export type NewPerformerScorerProgressParams = z.infer<typeof insertPerformerScorerProgressParams>;
export type UpdatePerformerScorerProgressParams = z.infer<typeof updatePerformerScorerProgressParams>;
export type PerformerScorerProgressId = z.infer<typeof performerScorerProgressIdSchema>["id"];
    
// this type infers the return from getPerformerScorerProgresses() - meaning it will include any joins
export type CompletePerformerScorerProgress = Awaited<ReturnType<typeof getPerformerScorerProgresses>>["performerScorerProgresses"][number];

