import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4", {
  variants: {
    variant: {
      default: "border-transparent bg-secondary text-secondary-foreground",
      outline: "text-foreground",
      measured: "border-transparent bg-[#0ca30c]/15 text-[#006300] dark:text-[#5fd35f]",
      target: "border-transparent bg-muted text-muted-foreground",
      notmet: "border-transparent bg-[#d03b3b]/15 text-[#a32626] dark:text-[#f08c8c]",
      dropped: "border-transparent bg-muted text-muted-foreground line-through",
      river: "border-transparent bg-accent text-accent-foreground",
    },
  },
  defaultVariants: { variant: "default" },
});

export function Badge({ className, variant, ...props }: React.HTMLAttributes<HTMLSpanElement> & VariantProps<typeof badgeVariants>) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
