import * as Collapsible from "@radix-ui/react-collapsible";
import { useState } from "react";

interface Props {
  dataOperation: unknown;
  route: string;
}

export function OperationExpander({ dataOperation, route }: Props) {
  const [open, setOpen] = useState(false);

  if (route !== "data" || !dataOperation) return null;

  return (
    <Collapsible.Root open={open} onOpenChange={setOpen} className="mt-2">
      <Collapsible.Trigger className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200">
        <span>{open ? "▾" : "▸"}</span>
        <span>How this was computed</span>
      </Collapsible.Trigger>
      <Collapsible.Content>
        <pre className="mt-2 overflow-x-auto rounded-lg bg-gray-50 p-3 text-xs text-gray-700 dark:bg-gray-900 dark:text-gray-300">
          {JSON.stringify(dataOperation, null, 2)}
        </pre>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
