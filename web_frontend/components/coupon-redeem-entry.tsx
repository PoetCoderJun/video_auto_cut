"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { authClient } from "../lib/auth-client";
import { activateInviteCode } from "../lib/api";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type CouponRedeemResult = {
  already_activated: boolean;
  coupon_redeemed: boolean;
  granted_credits: number;
  balance: number;
};

type CouponRedeemEntryProps = {
  buttonClassName?: string;
  buttonVariant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link";
  onRedeemed?: (result: CouponRedeemResult) => void;
};

export default function CouponRedeemEntry({
  buttonClassName,
  buttonVariant = "ghost",
  onRedeemed,
}: CouponRedeemEntryProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);

  const resolveAccessToken = async (): Promise<string> => {
    const tokenResult = await (authClient as any).token();
    return String(tokenResult?.data?.token || "").trim();
  };

  const handleOpenChange = (nextOpen: boolean) => {
    setOpen(nextOpen);
    if (nextOpen) {
      setCode("");
    }
  };

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!code.trim()) {
      toast.error("请输入兑换码");
      return;
    }

    setLoading(true);
    try {
      const token = await resolveAccessToken();
      if (!token) {
        throw new Error("请先登录后再兑换");
      }

      const activation = await activateInviteCode(code.trim().toUpperCase(), token);
      setOpen(false);
      setCode("");
      onRedeemed?.(activation);
      toast.success(
        activation.granted_credits > 0
          ? `兑换成功，已到账 ${activation.granted_credits} 次额度`
          : `兑换成功，当前余额 ${activation.balance} 次`
      );
      router.push("/");
      router.refresh();
    } catch (err: any) {
      toast.error(err.message || "兑换失败，请重试");
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <Button
        type="button"
        variant={buttonVariant}
        className={buttonClassName}
        onClick={() => handleOpenChange(true)}
      >
        兑换码兑换
      </Button>
      <Dialog open={open} onOpenChange={handleOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>兑换码兑换</DialogTitle>
            <DialogDescription>当前账号已登录，输入兑换码后立即完成额度兑换。</DialogDescription>
          </DialogHeader>
          <form className="grid gap-4" onSubmit={handleSubmit}>
            <div className="grid gap-2">
              <Label htmlFor="redeem-code">兑换码</Label>
              <Input
                id="redeem-code"
                placeholder="请输入兑换码"
                type="text"
                autoCapitalize="characters"
                disabled={loading}
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                required
              />
            </div>
            <Button type="submit" disabled={loading}>
              {loading ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  兑换中...
                </>
              ) : (
                "确认兑换"
              )}
            </Button>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
