"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { toast } from "@/hooks/use-toast"
import { Loader2 } from "lucide-react"
import { mockAuth } from "@/lib/mock-auth"

interface ForgotPasswordFormProps {
  onSuccess?: () => void
  onLoginClick?: () => void
  isDialog?: boolean
}

export function ForgotPasswordForm({ onSuccess, onLoginClick, isDialog = false }: ForgotPasswordFormProps) {
  const router = useRouter()
  const [isLoading, setIsLoading] = useState(false)
  const [email, setEmail] = useState("")
  const [otp, setOtp] = useState("")
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [step, setStep] = useState<"email" | "verify" | "reset">("email")

  // 发送验证码
  const handleSendOtp = async () => {
    if (!email) {
      toast({
        title: "请输入邮箱",
        variant: "destructive",
      })
      return
    }

    try {
      setIsLoading(true)
      const { error } = await mockAuth.resetPasswordForEmail()

      if (error) throw error

      setStep("verify")
      toast({
        title: "验证码已发送",
        description: "请查看您的邮箱（模拟：使用123456作为验证码）",
      })
    } catch (error: any) {
      toast({
        title: "发送验证码失败",
        description: error.message,
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  // 验证OTP
  const handleVerifyOtp = async () => {
    if (!otp) {
      toast({
        title: "请输入验证码",
        variant: "destructive",
      })
      return
    }

    try {
      setIsLoading(true)
      // 模拟验证码验证
      if (otp === "123456" || otp === "") {
        setStep("reset")
        toast({
          title: "验证成功",
          description: "请设置新密码",
        })
      } else {
        throw new Error("验证码错误")
      }
    } catch (error: any) {
      toast({
        title: "验证失败",
        description: error.message,
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  // 重置密码
  const handleResetPassword = async () => {
    if (!password || !confirmPassword) {
      toast({
        title: "请填写所有字段",
        variant: "destructive",
      })
      return
    }

    if (password !== confirmPassword) {
      toast({
        title: "两次输入的密码不一致",
        variant: "destructive",
      })
      return
    }

    try {
      setIsLoading(true)
      const { error } = await mockAuth.updateUser({
        password,
      })

      if (error) throw error

      toast({
        title: "密码已重置",
        description: "请使用新密码登录",
      })

      if (onSuccess) {
        onSuccess()
      } else {
        router.push("/auth/login")
      }
    } catch (error: any) {
      toast({
        title: "重置密码失败",
        description: error.message,
        variant: "destructive",
      })
    } finally {
      setIsLoading(false)
    }
  }

  const handleLogin = () => {
    if (onLoginClick) {
      onLoginClick()
    } else if (!isDialog) {
      router.push("/auth/login")
    }
  }

  return (
    <Card className={isDialog ? "border-0 shadow-none" : ""}>
      <CardHeader>
        <CardTitle className="text-2xl text-center">忘记密码</CardTitle>
        <CardDescription className="text-center">
          {step === "email" && "请输入您的邮箱以获取验证码"}
          {step === "verify" && "请输入您收到的验证码"}
          {step === "reset" && "请设置新密码"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {step === "email" && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="email">邮箱</Label>
              <Input
                id="email"
                type="email"
                placeholder="请输入邮箱"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <Button className="w-full" onClick={handleSendOtp} disabled={isLoading}>
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              获取验证码
            </Button>
          </div>
        )}

        {step === "verify" && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="otp">验证码</Label>
              <Input
                id="otp"
                placeholder="请输入验证码"
                value={otp}
                onChange={(e) => setOtp(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep("email")} disabled={isLoading}>
                返回
              </Button>
              <Button onClick={handleVerifyOtp} disabled={isLoading}>
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                验证
              </Button>
            </div>
          </div>
        )}

        {step === "reset" && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new-password">新密码</Label>
              <Input
                id="new-password"
                type="password"
                placeholder="请输入新密码"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-new-password">确认新密码</Label>
              <Input
                id="confirm-new-password"
                type="password"
                placeholder="请再次输入新密码"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                disabled={isLoading}
              />
            </div>
            <div className="flex justify-between">
              <Button variant="outline" onClick={() => setStep("verify")} disabled={isLoading}>
                返回
              </Button>
              <Button onClick={handleResetPassword} disabled={isLoading}>
                {isLoading ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
                重置密码
              </Button>
            </div>
          </div>
        )}
      </CardContent>
      <CardFooter className="flex justify-center">
        <Button variant="link" onClick={handleLogin}>
          返回登录
        </Button>
      </CardFooter>
    </Card>
  )
}
