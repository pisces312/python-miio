#!/usr/bin/env python
"""小米云端登录 - 浏览器模式

当 miiocli cloud 因验证码/二次验证失败时，使用此脚本通过浏览器完成登录。

流程：
1. 输入小米账号密码
2. 脚本生成 JS 代码片段
3. 在浏览器中访问 account.xiaomi.com，按 F12 → Console
4. 粘贴运行 JS 代码
5. 如果需要二次验证，在浏览器中完成后再次运行
6. 脚本自动提取令牌并获取设备列表

用法: python browser_login.py
"""
import hashlib
import json

from miio.miutils import get_session, gen_nonce, signed_nonce, generate_enc_params, decrypt_rc4


def get_devices(session, user_id, service_token, ssecurity, country='cn'):
    url = f"https://{'' if country == 'cn' else country + '.'}api.io.mi.com/app/home/device_list"
    session.cookies.update({
        'userId': str(user_id),
        'yetAnotherServiceToken': service_token,
        'serviceToken': service_token,
        'locale': 'zh_CN',
        'channel': 'MI_APP_STORE',
    })
    params = {'data': json.dumps({
        "getVirtualModel": True,
        "getHuamiDevices": 1,
        "get_split_device": False,
        "support_smart_home": True
    })}
    nonce = gen_nonce()
    s_nonce = signed_nonce(ssecurity, nonce)
    post_data = generate_enc_params(url, "POST", s_nonce, nonce, params, ssecurity)
    resp = session.post(url, data=post_data)
    return json.loads(decrypt_rc4(signed_nonce(ssecurity, post_data["_nonce"]), resp.text))


def make_js_snippet(username, pwd_hash):
    return (
        f"(async()=>{{"
        f"const r=await fetch('https://account.xiaomi.com/pass/serviceLoginAuth2',{{"
        f"method:'POST',"
        f"headers:{{'Content-Type':'application/x-www-form-urlencoded'}},"
        f"body:'sid=xiaomiio&hash={pwd_hash}"
        f"&callback=https%3A%2F%2Fsts.api.io.mi.com%2Fsts"
        f"&qs=%3Fsid%3Dxiaomiio%26_json%3Dtrue"
        f"&user={username}&_json=true',"
        f"credentials:'include'}});"
        f"let t=await r.text();"
        f"t=t.replace('&&&START&&&','');"
        f"const d=JSON.parse(t);"
        f"console.log(JSON.stringify(d));"
        f"}})()"
    )


def parse_response(raw):
    raw = raw.strip().replace("&&&START&&&", "")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def main():
    print("=" * 60)
    print("小米云端登录 - 浏览器模式")
    print("=" * 60)

    username = input("\n小米账号 (手机号): ").strip()
    password = input("密码: ").strip()
    pwd_hash = hashlib.md5(password.encode()).hexdigest().upper()

    js_code = make_js_snippet(username, pwd_hash)

    print("\n" + "-" * 60)
    print("步骤 1: 在浏览器中访问 https://account.xiaomi.com")
    print("步骤 2: 按 F12 → Console")
    print("步骤 3: 粘贴运行以下代码：")
    print("-" * 60)
    print(f"\n  {js_code}\n")

    raw = input("粘贴输出内容: ").strip()
    data = parse_response(raw)

    if not data:
        print("JSON 解析失败")
        return

    # 2FA 循环处理
    for attempt in range(3):
        notification_url = data.get('notificationUrl', '')
        if not notification_url or 'ssecurity' in data:
            break

        print(f"\n需要二次验证！请在浏览器中打开以下链接完成验证：")
        print(f"\n  {notification_url}\n")
        input("验证完成后，按回车键继续...")

        print("\n请再次在 Console 中运行同样的代码：")
        print(f"\n  {js_code}\n")
        raw = input("粘贴输出内容: ").strip()
        data = parse_response(raw)
        if not data:
            print("JSON 解析失败")
            return

    if data.get('result') != 'ok':
        print(f"登录响应异常: {data.get('description', data)}")
        return

    ssecurity = data.get('ssecurity')
    user_id = data.get('userId')
    location = data.get('location')

    if not ssecurity:
        print("未获取到 ssecurity，响应：")
        print(json.dumps(data, indent=2, ensure_ascii=False))
        return

    # 从 location URL 获取 serviceToken
    service_token = None
    if location:
        print(f"\n正在获取 serviceToken...")
        session = get_session()
        session.cookies.update({'userId': str(user_id)})
        resp = session.get(location)
        service_token = resp.cookies.get('serviceToken')

    if not service_token:
        print("无法自动获取 serviceToken，请在 Console 中运行: document.cookie")
        cookie_str = input("粘贴 cookie: ").strip()
        for item in cookie_str.split(';'):
            if 'serviceToken' in item:
                service_token = item.split('=', 1)[1].strip()

    if not service_token:
        print("无法获取 serviceToken")
        return

    print(f"\n提取成功:")
    print(f"  userId: {user_id}")
    print(f"  ssecurity: {ssecurity[:20]}...")
    print(f"  serviceToken: {service_token[:20]}...")

    # 获取设备列表
    country = input("\n服务器区域 (cn/de/sg/us) [cn]: ").strip() or 'cn'
    print(f"\n正在获取设备列表...")
    try:
        result = get_devices(get_session(), user_id, service_token, ssecurity, country)
        devices = result.get('result', {}).get('list', [])
        print(f"\n找到 {len(devices)} 个设备：")
        print("-" * 60)
        for dev in devices:
            name = dev.get('name', '未知')
            model = dev.get('model', '未知')
            did = dev.get('did', '未知')
            token = dev.get('token', '未知')
            ip = dev.get('localip', '未知')
            online = '在线' if dev.get('isOnline') else '离线'
            print(f"  {name} ({model})")
            print(f"    DID: {did}  Token: {token}")
            print(f"    IP: {ip} [{online}]")
    except Exception as e:
        print(f"获取设备失败: {e}")


if __name__ == "__main__":
    main()
