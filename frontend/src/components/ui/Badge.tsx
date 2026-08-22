import React from "react";
import { cn } from "@/lib/utils";

interface BadgeProps {
  children: React.ReactNode;
  variant?: "amber" | "stone" | "emerald" | "orange" | "outline";
  className?: string;
  icon?: React.ReactNode;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = "stone",
  className,
  icon,
}) => {
  const variantStyles = {
    amber: "bg-amber-100/90 text-amber-900 border-amber-200/80",
    stone: "bg-stone-100 text-stone-700 border-stone-200",
    emerald: "bg-emerald-100/90 text-emerald-900 border-emerald-200/80",
    orange: "bg-orange-100/90 text-orange-900 border-orange-200/80",
    outline: "bg-white text-stone-600 border-stone-200",
  };

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium border",
        variantStyles[variant],
        className
      )}
    >
      {icon && <span className="shrink-0">{icon}</span>}
      {children}
    </span>
  );
};
