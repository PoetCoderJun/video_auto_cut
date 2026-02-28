import Image from "next/image";

import { Card, CardContent } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type FounderCardProps = {
  className?: string;
};

export default function FounderCard({ className }: FounderCardProps) {
  return (
    <Card className={cn("text-center shadow-lg", className)}>
      <CardContent className="pt-8">
        <div className="relative mx-auto mb-4 h-20 w-20 overflow-hidden rounded-full border-2 border-border">
          <a
            href="https://xhslink.com/m/2CUIT8iyntn"
            target="_blank"
            rel="noopener noreferrer"
          >
            <Image src="/photo.jpg" alt="Jun" fill className="object-cover" />
          </a>
        </div>
        <h3 className="mb-2 text-lg font-bold text-foreground">诗人程序员Jun</h3>
        <div className="mb-6 inline-flex items-center gap-2 rounded-full bg-muted px-3 py-1 text-xs font-medium text-muted-foreground">
          <span>AI builder in HK</span>
          <span className="h-1 w-1 rounded-full bg-muted-foreground/30" />
          <span>Vibe coding 主理人</span>
        </div>
        <p className="text-sm text-muted-foreground">
          合作 / 工作机会等，欢迎关注{" "}
          <a
            href="https://xhslink.com/m/2CUIT8iyntn"
            target="_blank"
            rel="noopener noreferrer"
            className="font-semibold text-foreground underline hover:text-primary"
          >
            小红书
          </a>{" "}
          随时私信我。
        </p>
      </CardContent>
    </Card>
  );
}
