function e() {
    try {
        const e = "cookietest",
            t = String(Math.random());
        return document.cookie = `${e}=${t}; path=/; SameSite=Lax`, !!document.cookie.includes(`${e}=${t}`) && (document.cookie = `${e}=; path=/; max-age=0; SameSite=Lax`, !0)
    } catch {
        return !1
    }
}! function() {
    const e = document.createElement("link").relList;
    if (!(e && e.supports && e.supports("modulepreload"))) {
        for (const e of document.querySelectorAll('link[rel="modulepreload"]')) t(e);
        new MutationObserver(e => {
            for (const r of e)
                if ("childList" === r.type)
                    for (const e of r.addedNodes) "LINK" === e.tagName && "modulepreload" === e.rel && t(e)
        }).observe(document, {
            childList: !0,
            subtree: !0
        })
    }

    function t(e) {
        if (e.ep) return;
        e.ep = !0;
        const t = function(e) {
            const t = {};
            return e.integrity && (t.integrity = e.integrity), e.referrerPolicy && (t.referrerPolicy = e.referrerPolicy), "use-credentials" === e.crossOrigin ? t.credentials = "include" : "anonymous" === e.crossOrigin ? t.credentials = "omit" : t.credentials = "same-origin", t
        }(e);
        fetch(e.href, t)
    }
}();
const t = new class {
        get(e, t) {
            try {
                this.checkLSSupport();
                const r = window.localStorage.getItem(e);
                return r && "string" == typeof r ? JSON.parse(r) : t || null
            } catch (r) {
                return null
            }
        }
        set(e, t) {
            try {
                this.checkLSSupport(), window.localStorage.setItem(e, JSON.stringify(t))
            } catch (r) {
                return !1
            }
            return !0
        }
        remove(e) {
            try {
                this.checkLSSupport(), window.localStorage.removeItem(e)
            } catch (t) {
                return !1
            }
            return !0
        }
        checkLSSupport() {
            if (!window.localStorage) throw new Error("LocalStorage is not allowed.")
        }
    },
    r = "x_wbaas_token_treshold",
    n = {
        tries: 0,
        lastTryTime: Date.now()
    },
    i = new class {
        constructor(e) {
            this.lsInstance = e, this.lsInstance.get(r) || this.lsInstance.set(r, n)
        }
        getState() {
            return this.lsInstance.get(r, n)
        }
        registerAttempt() {
            const e = this.getState();
            e.tries++, this.setState(e)
        }
        isCreateTokenAllowed() {
            const e = this.lsInstance.get(r),
                {
                    tries: t,
                    lastTryTime: n
                } = e;
            let i = !0;
            return t < 3 || t >= 3 && (i = !1, this.isThresholdReached(n) && (this.resetLimits(), i = !0)), i
        }
        resetLimits() {
            this.setState(n)
        }
        setState(e) {
            this.lsInstance.set(r, e)
        }
        isThresholdReached(e) {
            const t = Date.now(),
                n = e < t,
                i = e > Date.UTC(2024, 4, 25);
            var o;
            return "number" == typeof(o = e) && isFinite(o) && Math.floor(o) === o && n && i ? Math.max(0, t - e) >= 6e4 : (this.lsInstance.set(r, {
                tries: 3,
                lastTryTime: Date.now()
            }), !1)
        }
    }(t),
    o = t => {
        const r = {
            t_elapsed: window.LOAD_START ? Date.now() - window.LOAD_START : 0,
            reqIp: (null === (n = document.documentElement) || void 0 === n ? void 0 : n.dataset.reqIp) || "",
            reqId: (null === (o = document.documentElement) || void 0 === o ? void 0 : o.dataset.reqUuid) || "",
            tries: i.getState().tries,
            lastTryTime: i.getState().lastTryTime
        };
        var n, o, s;
        return {
            type: "ERROR",
            message: `Error Main: ${s=t,"string"==typeof s?s:JSON.stringify(s,Object.getOwnPropertyNames(s))}`,
            url: window.location.href,
            ua: window.navigator.userAgent,
            extra: {
                data: JSON.stringify(r),
                cookieEnabled: `${e()}`
            }
        }
    };
var s, a;
(a = s || (s = {})).EN = "en", a.RU = "ru", a.AM = "am", a.AZ = "az", a.KA = "ka", a.TG = "tg", a.HY = "hy", a.UZ = "uz", a.KK = "kk", a.KY = "ky";
var c = s.EN;

function l(e) {
    if (! function(e) {
            if (!e) return !1;
            var t = e.trim();
            return t.length > 0 && !t.includes("{{")
        }(e)) return null;
    var t = e.trim().toLowerCase().replace(/_/g, "-").split("-")[0];
    return t.length > 0 ? t : null
}
var d, u, h, p, g, m, b, f, y, v, w, S = Object.values(s),
    k = {
        en: s.EN,
        ru: s.RU,
        am: s.AM,
        az: s.AZ,
        ka: s.KA,
        tg: s.TG,
        hy: s.HY,
        uz: s.UZ,
        kk: s.KK,
        ky: s.KY
    };

function O(e) {
    return S.includes(e)
}
var M = "checkingBrowserTitle",
    x = "cookiesAreNotAllowed",
    T = "tryingAgainThrough",
    E = "newTry",
    F = "somethingWentWrong",
    P = "suspiciousActivity",
    B = "whatToDo",
    C = "whatToDoStep1",
    A = "whatToDoStep2",
    _ = "contactSupport",
    j = "tokenIssueSubject",
    R = "tokenIssueIntro",
    I = "tokenIssueHelp",
    N = "commentLabel",
    L = "serviceInfoLabel",
    D = "serviceInfoNotice",
    U = ((d = {})[M] = "Checking your browser", d[x] = "Please enable cookies in your browser settings and reload the page to continue using this website", d[T] = "Try again in", d[E] = "Trying again...", d[F] = "Something went wrong", d[P] = "Suspicious activity detected. Please wait.", d[B] = "What's next", d[C] = "The page will refresh automatically, so please wait and don't take any action", d[A] = "If the issue persists, clear your browser cache and cookies, then reload the page", d[_] = "If none of the above helps, please contact Support", d[j] = "Token issuance error", d[R] = "Tell us what happened before the error occurred.", d[I] = "It'll help us fix it faster.", d[N] = "Comment:", d[L] = "——— SERVICE INFORMATION ———", d[D] = "Please don't delete it. It's required for diagnostics.", d),
    z = ((u = {})[s.EN] = U, u[s.RU] = ((h = {})[M] = "Проверяем браузер", h[x] = "Для работы сайта необходимо включить cookies в настройках вашего браузера и перезагрузить страницу.", h[T] = "Новая попытка через", h[E] = "Пробуем еще раз...", h[F] = "Что-то не так...", h[P] = "Подозрительная активность. Пожалуйста, подождите.", h[B] = "Что делать", h[C] = "Подождите, страница обновится автоматически", h[A] = "Если не помогло — очистите кэш и cookie в браузере, потом перезагрузите страницу", h[_] = "Ошибка не исчезла? Пишите в поддержку", h[j] = "Ошибка при выдаче токена", h[R] = "Расскажите, что произошло перед ошибкой.", h[I] = "Это поможет нам быстрее её исправить.", h[N] = "Комментарий:", h[L] = "——— СЛУЖЕБНАЯ ИНФОРМАЦИЯ ———", h[D] = "Пожалуйста, не удаляйте её — она нужна для диагностики.", h), u[s.AM] = ((p = {})[M] = "አሳሽዎን በመፈተሽ ላይ ነን", p[x] = "ይህን ጣቢያ ለመጠቀም በአሳሽዎ ቅንብሮች ውስጥ cookies ን ያብሩ እና ገጹን እንደገና ይጫኑ።", p[T] = "እንደገና ለመሞከር የቀረው", p[E] = "እንደገና በመሞከር ላይ...", p[F] = "አንድ ችግር አለ...", p[P] = "አጠራጣሪ እንቅስቃሴ ታይቷል። እባክዎ ይጠብቁ።", p[B] = "ምን ማድረግ አለብን", p[C] = "እባክዎ ይጠብቁ፣ ገጹ በራሱ ይታደሳል", p[A] = "ካልሰራ — በአሳሹ ውስጥ ያለውን cache እና cookie ያጽዱ, ከዚያ ገጹን እንደገና ያስጀምሩ", p[_] = "ስህተቱ አልጠፋም? ለድጋፍ ይጻፉ", p[j] = "ቶክን በሚሰጥበት ጊዜ ስህተት ተከስቷል", p[R] = "ከስህተቱ በፊት ምን እንደተፈጠረ ይንገሩን።", p[I] = "ይህ ችግሩን በፍጥነት እንድንፈታ ይረዳናል።", p[N] = "አስተያየቶች", p[L] = "——— የአገልግሎት መረጃ ———", p[D] = "እባክዎ አያስወግዱት — ለምርመራ ያስፈልጋል።", p), u[s.AZ] = ((g = {})[M] = "Brauzeriniz yoxlanılır", g[x] = "Saytdan istifadə etmək üçün brauzer parametrlərində kukiləri aktiv edin və səhifəni yenidən yükləyin.", g[T] = "Yenidən cəhdə qədər", g[E] = "Yenidən cəhd edirik...", g[F] = "Nəsə səhvdir...", g[P] = "Şübhəli fəaliyyət. Zəhmət olmasa, gözləyin.", g[B] = "Nə etməli", g[C] = "Zəhmət olmasa gözləyin, səhifə avtomatik yenilənəcək", g[A] = "Bu kömək etmədisə, brauzer keşini və kukilərini təmizləyin, sonra səhifəni yenidən yükləyin", g[_] = "Xəta qalır? Dəstəyə yazın", g[j] = "Token verilməsi zamanı xəta", g[R] = "Xətadan əvvəl nə baş verdiyini bizə yazın.", g[I] = "Bu, onu daha tez düzəltməyimizə kömək edəcək.", g[N] = "Şərh:", g[L] = "——— XİDMƏT MƏLUMATI ———", g[D] = "Zəhmət olmasa bunu silməyin — diaqnostika üçün lazımdır.", g), u[s.KA] = ((m = {})[M] = "ვამოწმებთ ბრაუზერს", m[x] = "საიტთან მუშაობისთვის საჭიროა ბრაუზერის პარამეტრებიდან გაააქტიუროთ ქუქიები და გადატვირთოთ გვერდი.", m[T] = "ახალი მცდელობა", m[E] = "კიდევ ერთხელ ვცდით...", m[F] = "დაფიქსირდა შეცდომა...", m[P] = "საეჭვო აქტივობა. გთხოვთ დაელოდოთ.", m[B] = "რა უნდა გააკეთოთ", m[C] = "დაელოდეთ, გვერდი ავტომატურად განახლდება", m[A] = "თუ პრობლემა არ აღმოიფხვრა, გაასუფთავეთ ბრაუზერის ქეში და ქუქიები, შემდეგ ხელახლა ჩატვირთეთ გვერდი", m[_] = "შეცდომა არ აღმოიფხვრა? მიწერეთ მხარდაჭერის გუნდს", m[j] = "ტოკენის გაცემისას დაფიქსირდა შეცდომა", m[R] = "მოგვიყევით, რა მოხდა შეცდომამდე.", m[I] = "ეს დაგვეხმარება მის უფრო სწრაფად გამოსწორებაში.", m[N] = "კომენტარი:", m[L] = "——— სერვისის ინფორმაცია ———", m[D] = "გთხოვთ არ წაშალოთ – ეს საჭიროა დიაგნოსტიკისთვის.", m), u[s.TG] = ((b = {})[M] = "Мо браузери шуморо месанҷем", b[x] = "Барои кори сомона cookie-ҳоро дар танзимоти браузератон фаъол кунед ва саҳифаро аз нав бор кунед.", b[T] = "Кӯшиши нав пас аз", b[E] = "Боз кӯшиш мекунем...", b[F] = "Чизе нодуруст шуд...", b[P] = "Фаъолияти шубҳанок. Лутфан интизор шавед.", b[B] = "Чӣ бояд кард", b[C] = "Интизор шавед, саҳифа худкор аз нав бор мешавад", b[A] = "Агар кумак накард, кэш ва cookie-ҳои браузерро тоза кунед, баъд саҳифаро аз нав бор кунед", b[_] = "Хатогӣ нест нашуд? Ба хадамоти дастгирӣ нависед", b[j] = "Хатогӣ ҳангоми супоридани токен", b[R] = "Нависед, ки пеш аз хатогӣ чӣ рӯй дод.", b[I] = "Ин ба мо кӯмак мекунад, ки онро зудтар ислоҳ кунем.", b[N] = "Шарҳ:", b[L] = "——— МАЪЛУМОТИ ХИЗМАТӢ ———", b[D] = "Лутфан онро тоза накунед — он барои ташхис лозим аст.", b), u[s.HY] = ((f = {})[M] = "Ստուգում ենք դիտարկիչը", f[x] = "Կայքն օգտագործելու համար միացրեք cookies ֆայլերը ձեր դիտարկիչի կարգավորումներում և կրկին բեռնեք էջը։", f[T] = "Նոր փորձ՝", f[E] = "Նորից փորձենք...", f[F] = "Ինչ-որ բան այն չէ...", f[P] = "Կասկածելի ակտիվություն։ Խնդրում ենք սպասել։", f[B] = "Ինչ անել", f[C] = "Սպասեք, էջը ավտոմատ կթարմացվի", f[A] = "Եթե չօգնեց, մաքրեք դիտարկիչի քեշը և cookie ֆայլերը, ապա կրկին բեռնեք էջը", f[_] = "Սխալը չվերացա՞վ։ Գրեք աջակցման ծառայությանը", f[j] = "Թոքենի տրամադրման սխալ", f[R] = "Պատմեք, թե ինչ տեղի ունեցավ սխալից առաջ։", f[I] = "Դա կօգնի մեզ ավելի արագ ուղղել այն։", f[N] = "Մեկնաբանություն․", f[L] = "——— ԾԱՌԱՅՈՂԱԿԱՆ ՏԵՂԵԿՈՒԹՅՈՒՆՆԵՐ———", f[D] = "Խնդրում ենք չջնջել․ այն պետք է դիագնոստիկայի համար։", f), u[s.UZ] = ((y = {})[M] = "Brauzeringizni tekshiryapmiz", y[x] = "Saytdan foydalanish uchun brauzer sozlamalarida cookie-fayllarni yoqish va sahifani qayta yuklash zarur.", y[T] = "Yangi urinish", y[E] = "Qayta urinib ko‘ryapmiz...", y[F] = "Qandaydir xatolik...", y[P] = "Shubhali faollik. Iltimos, kuting.", y[B] = "Nima qilish kerak", y[C] = "Kuting, sahifa avtomatik ravishda yangilanadi", y[A] = "Agar yordam bermasa, brauzer keshini va cookie-fayllarni tozalang, so‘ng sahifani qayta yuklang", y[_] = "Xato yo‘qolmadimi? Yordam xizmatiga yozing", y[j] = "Tokenni berishda xatolik", y[R] = "Xatodan oldin nima yuz bo‘lganini yozib bering.", y[I] = "Bu uni tezroq tuzatishimizga yordam beradi.", y[N] = "Izoh:", y[L] = "——— XIZMAT MA’LUMOTI ———", y[D] = "Iltimos, uni o‘chirib tashlamang – u diagnostika uchun kerak.", y), u[s.KK] = ((v = {})[M] = "Браузеріңізді тексеріп жатырмыз", v[x] = "Сайттың жұмыс істеуі үшін браузер баптауларында cookie файлдарын қосып, бетті қайта жүктеңіз.", v[T] = "Қайта әрекет ету", v[E] = "Қайтадан байқап жатырмыз...", v[F] = "Бірдеңе дұрыс емес...", v[P] = "Күдікті белсенділік. Күте тұрыңыз.", v[B] = "Не істеу керек", v[C] = "Күте тұрыңыз, бет автоматты түрде жаңартылады", v[A] = "Егер көмектеспесе, браузер кэші мен cookie файлдарын тазалап, бетті қайта жүктеңіз", v[_] = "Қате жойылмады ма? Қолдауға жазыңыз", v[j] = "Токен беру кезіндегі қате", v[R] = "Қатеге дейін не болғанын айтып беріңіз.", v[I] = "Бұл оны тезірек түзетуімізге көмектеседі.", v[N] = "Түсініктеме:", v[L] = "——— ҚЫЗМЕТТІК АҚПАРАТ ———", v[D] = "Оны өшірмеңіз — ол диагностика үшін қажет.", v), u[s.KY] = ((w = {})[M] = "Серепчиңизди текшерип жатабыз", w[x] = "Сайт иштеши үчүн серепчи жөндөөлөрүндө cookie файлдарын күйгүзүп, баракты кайра жүктөңүз.", w[T] = "Жаңы аракет убактысы:", w[E] = "Дагы бир жолу аракет кылып жатабыз...", w[F] = "Бир нерсе туура эмес...", w[P] = "Шектүү аракет. Сураныч, күтө туруңуз.", w[B] = "Эмне кылуу керек", w[C] = "Күтө туруңуз, барак автоматтык түрдө жаңыланат", w[A] = "Эгер жардам бербесе, серепчинин кешин жана cookie файлдарын тазалап, баракты кайра жүктөңүз", w[_] = "Ката жоголгон жокпу? Колдоого жазыңыз", w[j] = "Токен берүү учурундагы ката", w[R] = "Катага чейин эмне болгонун айтып бериңиз.", w[I] = "Бул аны тезирээк оңдоого жардам берет.", w[N] = "Комментарий:", w[L] = "——— КЫЗМАТТЫК МААЛЫМАТ ———", w[D] = "Сураныч, муну өчүрбөңүз — бул диагностика үчүн керек.", w), u);
const q = function() {
        var e, t = l(document.documentElement.lang);
        if (t && O(t)) return k[t];
        var r = l(null === (e = null === document || void 0 === document ? void 0 : document.documentElement) || void 0 === e ? void 0 : e.lang);
        return r && O(r) ? k[r] : function(e) {
            var t, r;
            void 0 === e && (e = c);
            var n = "object" == typeof window ? window.navigator : void 0;
            if (!n) return e;
            var i = Array.isArray(n.languages) && n.languages.length > 0 ? n.languages : [n.language];
            try {
                for (var o = function(e) {
                        var t = "function" == typeof Symbol && Symbol.iterator,
                            r = t && e[t],
                            n = 0;
                        if (r) return r.call(e);
                        if (e && "number" == typeof e.length) return {
                            next: function() {
                                return e && n >= e.length && (e = void 0), {
                                    value: e && e[n++],
                                    done: !e
                                }
                            }
                        };
                        throw new TypeError(t ? "Object is not iterable." : "Symbol.iterator is not defined.")
                    }(i), s = o.next(); !s.done; s = o.next()) {
                    var a = l(s.value);
                    if (a && O(a)) return k[a]
                }
            } catch (d) {
                t = {
                    error: d
                }
            } finally {
                try {
                    s && !s.done && (r = o.return) && r.call(o)
                } finally {
                    if (t) throw t.error
                }
            }
            return e
        }()
    }(),
    H = (V = z, K = q, void 0 === W && (W = c), function(e) {
        return function(e, t, r, n) {
            var i;
            return void 0 === n && (n = c), null !== (i = e[r][t]) && void 0 !== i ? i : e[n][t]
        }(V, e, K, W)
    });
var V, K, W;

function G(e, ...t) {
    const r = e;
    if ("function" != typeof r.replaceChildren) {
        for (; e.firstChild;) e.removeChild(e.firstChild);
        t.forEach(t => {
            "string" != typeof t ? e.appendChild(t) : e.appendChild(document.createTextNode(t))
        })
    } else r.replaceChildren(...t)
}

function Z(e) {
    const t = document.createElement("div");
    t.innerHTML = `\n      <div class="support">\n        <svg\n          class="support-logo"\n          width="100"\n          height="100"\n          viewBox="0 0 100 100"\n          fill="none"\n          xmlns="http://www.w3.org/2000/svg"\n        >\n          <path\n            d="M51.6852 75.9854C58.5299 73.4069 85.3546 60.5592 86.5418 17.243C86.5924 15.3976 85.6274 13.6535 84.0564 12.6782C63.271 -0.226077 36.9426 -0.226076 16.1572 12.6782C14.5862 13.6535 13.6212 15.3976 13.6718 17.243C14.859 60.5592 41.6837 73.4069 48.5284 75.9854C49.5503 76.3704 50.6633 76.3704 51.6852 75.9854Z"\n            fill="url(#paint0_linear_9028_11756)"\n          />\n          <g data-figma-bg-blur-radius="9.27278">\n            <path\n              d="M13.9134 27.8499L10.6156 29.7302C8.72144 30.8101 7.53858 32.8483 7.61053 35.0238C9.16345 81.9803 41.4117 95.3443 48.6667 97.7616C49.6209 98.0795 50.594 98.0795 51.5481 97.7616C58.8031 95.3443 91.0514 81.9803 92.6043 35.0238C92.6763 32.8483 91.4934 30.8101 89.5993 29.7302L86.3014 27.8499C63.8738 15.0627 36.3411 15.0627 13.9134 27.8499Z"\n              fill="url(#paint1_linear_9028_11756)"\n              fill-opacity="0.5"\n            />\n            <path\n              d="M14.1611 28.2839C36.4352 15.5844 63.7797 15.5844 86.0537 28.2839L89.3516 30.1648C91.0908 31.1564 92.1701 33.0246 92.1045 35.0076C91.3321 58.3605 82.9327 73.3231 73.8545 82.7478C64.7663 92.1828 54.9712 96.0935 51.3896 97.2869C50.5382 97.5705 49.6766 97.5705 48.8252 97.2869C45.2437 96.0935 35.4485 92.1828 26.3604 82.7478C17.2822 73.3231 8.88273 58.3605 8.11035 35.0076C8.04477 33.0246 9.12408 31.1564 10.8633 30.1648L14.1611 28.2839Z"\n              stroke="url(#paint2_linear_9028_11756)"\n              stroke-opacity="0.7"\n            />\n          </g>\n          <path\n            d="M40.5008 50.4126C40.4957 50.5315 40.5151 50.6501 40.5577 50.7612C40.6003 50.8723 40.6652 50.9735 40.7484 51.0587C40.8317 51.1438 40.9315 51.211 41.0418 51.2563C41.152 51.3015 41.2704 51.3237 41.3896 51.3216H44.432C44.941 51.3216 45.3466 50.9058 45.413 50.4016C45.7449 47.9875 47.4044 46.2284 50.3621 46.2284C52.892 46.2284 55.2079 47.4907 55.2079 50.5267C55.2079 52.8635 53.8287 53.9381 51.6492 55.5721C49.1672 57.3716 47.2016 59.4729 47.3417 62.8844L47.3528 63.6829C47.3567 63.9244 47.4555 64.1546 47.628 64.324C47.8005 64.4934 48.0328 64.5883 48.2748 64.5882H51.2656C51.5101 64.5882 51.7446 64.4913 51.9175 64.3188C52.0904 64.1462 52.1876 63.9122 52.1876 63.6682V63.2818C52.1876 60.6395 53.1944 59.8704 55.9123 57.8132C58.1582 56.1094 60.5 54.2178 60.5 50.247C60.5 44.6864 55.7943 42 50.6424 42C45.9699 42 40.8511 44.1712 40.5008 50.4126ZM46.2428 69.5886C46.2428 71.5501 47.8101 73 49.9675 73C52.2134 73 53.7586 71.5501 53.7586 69.5886C53.7586 67.5572 52.2097 66.1293 49.9638 66.1293C47.8101 66.1293 46.2428 67.5572 46.2428 69.5886Z"\n            fill="white"\n          />\n          <defs>\n            <linearGradient\n              id="paint0_linear_9028_11756"\n              x1="50.1068"\n              y1="3"\n              x2="50.1068"\n              y2="76.2742"\n              gradientUnits="userSpaceOnUse"\n            >\n              <stop stop-color="#C47DFF" />\n              <stop offset="1" stop-color="#BA14FF" />\n            </linearGradient>\n            <linearGradient\n              id="paint1_linear_9028_11756"\n              x1="50.1074"\n              y1="134.087"\n              x2="54.7459"\n              y2="18.4888"\n              gradientUnits="userSpaceOnUse"\n            >\n              <stop stop-color="#DBD2FE" />\n              <stop offset="1" stop-color="#F3EAFF" />\n            </linearGradient>\n            <linearGradient\n              id="paint2_linear_9028_11756"\n              x1="30.5"\n              y1="18"\n              x2="57.5"\n              y2="106.5"\n              gradientUnits="userSpaceOnUse"\n            >\n              <stop stop-color="white" />\n              <stop offset="1" stop-color="#E0C3FF" />\n            </linearGradient>\n          </defs>\n        </svg>\n        <div class="support-header">\n          <h1 class="support-title">${H(F)}</h1>\n          <p class="support-subtitle">${H(P)}</p>\n          <p id="r-uuid" class="support-id" data-req-uuid="{{ReqUUID}}">ID: {{ReqUUID}}</p>\n          <p id="r-ip" class="support-id" data-req-ip="{{ReqIp}}">IP: {{ReqIp}}</p>\n          <div class="support-countdown">\n            <svg\n              class="support-countdown-icon clock-icon"\n              width="18"\n              height="18"\n              viewBox="0 0 18 18"\n              fill="none"\n              xmlns="http://www.w3.org/2000/svg"\n            >\n              <path\n                d="M11.59 11.6362C12.114 11.8108 12.6803 11.5277 12.8549 11.0037C13.0296 10.4798 12.7464 9.91346 12.2225 9.73882L11.9062 10.6875L11.59 11.6362ZM9.375 9.84375H8.375C8.375 10.2742 8.65043 10.6563 9.05877 10.7924L9.375 9.84375ZM10.375 6.31565C10.375 5.76337 9.92728 5.31565 9.375 5.31565C8.82272 5.31565 8.375 5.76337 8.375 6.31565H9.375H10.375ZM11.9062 10.6875L12.2225 9.73882L9.69123 8.89507L9.375 9.84375L9.05877 10.7924L11.59 11.6362L11.9062 10.6875ZM9.375 9.84375H10.375V6.31565H9.375H8.375V9.84375H9.375ZM16.125 9H15.125C15.125 12.1756 12.5506 14.75 9.375 14.75V15.75V16.75C13.6552 16.75 17.125 13.2802 17.125 9H16.125ZM9.375 15.75V14.75C6.19936 14.75 3.625 12.1756 3.625 9H2.625H1.625C1.625 13.2802 5.09479 16.75 9.375 16.75V15.75ZM2.625 9H3.625C3.625 5.82436 6.19936 3.25 9.375 3.25V2.25V1.25C5.09479 1.25 1.625 4.71979 1.625 9H2.625ZM9.375 2.25V3.25C12.5506 3.25 15.125 5.82436 15.125 9H16.125H17.125C17.125 4.71979 13.6552 1.25 9.375 1.25V2.25Z"\n                fill="#B061FF"\n              />\n            </svg>\n            <svg\n              class="support-countdown-icon load-icon is-hidden"\n              width="18"\n              height="18"\n              viewBox="0 0 20 20"\n              fill="none"\n              xmlns="http://www.w3.org/2000/svg"\n            >\n              <path\n                d="M11.125 4.75V1.75M11.125 18.25V14.25M15.875 9.5H17.625M2.375 9.5H6.375M14.4841 6.14142L15.8755 4.75M4.9372 15.6873L7.76563 12.8589M14.4841 12.8586L15.875 14.2495M4.9372 3.31269L7.76563 6.14111"\n                stroke="#B061FF"\n                stroke-width="2"\n                stroke-linecap="round"\n                stroke-linejoin="round"\n              />\n            </svg>\n\n            <p class="support-countdown-text">${H(T)} 00:59</p>\n          </div>\n        </div>\n        <div class="support-info">\n          <p class="support-info-title">${H(B)}:</p>\n          <ol class="support-info-list">\n            <li class="support-info-line">${H(C)}.</li>\n            <li class="support-info-line">${H(A)}.</li>\n            <li class="support-info-line">\n              ${H(_)}:\n                <button class="support-mail-btn">\n                  <span class="support-mail-btn-text">captcha-support@rwb.ru</span>\n                  <svg\n                    class="mail-icon"\n                    width="16"\n                    height="16"\n                    viewBox="0 0 16 16"\n                    fill="none"\n                    xmlns="http://www.w3.org/2000/svg"\n                  >\n                    <path\n                      d="M7.25 2H4.25C3.00736 2 2 3.00735 2 4.24999V11.75C2 12.9926 3.00736 14 4.25 14H11.75C12.9926 14 14 12.9926 14 11.75V8.74996M10.2496 2.00018L14 2M14 2V5.37507M14 2L7.62445 8.37478"\n                      stroke="#4585FF"\n                      stroke-width="2"\n                      stroke-linecap="round"\n                      stroke-linejoin="round"\n                    />\n                  </svg>\n                </button>\n              </li>\n          </ol>\n        </div>\n      </div>\n  `,
        function(e) {
            const {
                reqUuid: t,
                reqIp: r
            } = function() {
                const {
                    reqUuid: e,
                    reqIp: t
                } = document.documentElement.dataset, r = document.documentElement.lang;
                return {
                    reqUuid: Y(e),
                    reqIp: Y(t),
                    language: Y(r)
                }
            }(), n = e.querySelector("#r-uuid");
            n && (t ? (n.dataset.reqUuid = t, n.textContent = `ID: ${t}`) : (n.textContent = "ID: -", n.removeAttribute("data-req-uuid")));
            const i = e.querySelector("#r-ip");
            i && (r ? (i.dataset.reqIp = r, i.textContent = `IP: ${r}`) : (i.textContent = "IP: -", i.removeAttribute("data-req-ip")))
        }(t);
    const r = document.querySelector(".w");
    if (!r) throw new Error("Main container not found");
    G(r, t),
        function(e) {
            const t = document.querySelector(".support-mail-btn"),
                r = document.querySelector(".support-countdown-text"),
                n = document.querySelector(".support-countdown .clock-icon"),
                o = document.querySelector(".support-countdown .load-icon");
            let s = null,
                a = null,
                c = 59;
            const l = () => {
                    null !== s && (window.clearInterval(s), s = null)
                },
                d = e => {
                    null == n || n.classList.toggle("is-hidden", e), null == o || o.classList.toggle("is-hidden", !e)
                },
                u = e => {
                    if (!r) return;
                    const t = e.toString().padStart(2, "0");
                    r.textContent = `${H(T)} 00:${t}`
                },
                h = (e = 59) => {
                    if (!r) return;
                    l(), null !== a && (window.clearTimeout(a), a = null);
                    const t = e >= 1 ? e : 59;
                    c = t, d(!1), u(c), s = window.setInterval(() => {
                        c -= 1, c >= 1 ? u(c) : (l(), r && (r.textContent = H(E), d(!0), c = 0))
                    }, 1e3);
                    const n = 1e3 * (t + 1);
                    a = window.setTimeout(() => {
                        i.resetLimits(), window.location.reload()
                    }, n)
                };
            if (r && h(), t) {
                const r = encodeURIComponent("Ошибка при выдаче токена"),
                    n = [H(R), H(I), "", H(N), "", "", "", "", H(L), "", H(D), "", e],
                    i = `mailto:captcha-support@rwb.ru?subject=${r}&body=${encodeURIComponent(n.join("\r\n"))}`;
                t.addEventListener("click", () => {
                    h(c >= 1 ? c : 59), window.location.href = i
                })
            }
        }(e)
}

function Y(e) {
    if (!e) return "";
    const t = e.trim();
    return !t || t.includes("{{") ? "" : t
}

function $(e) {
    return ($ = "function" == typeof Symbol && "symbol" == typeof Symbol.iterator ? function(e) {
        return typeof e
    } : function(e) {
        return e && "function" == typeof Symbol && e.constructor === Symbol && e !== Symbol.prototype ? "symbol" : typeof e
    })(e)
}

function J(e, t, r) {
    return (t = function(e) {
        var t = function(e) {
            if ("object" != $(e) || !e) return e;
            var t = e[Symbol.toPrimitive];
            if (void 0 !== t) {
                var r = t.call(e, "string");
                if ("object" != $(r)) return r;
                throw new TypeError("@@toPrimitive must return a primitive value.")
            }
            return String(e)
        }(e);
        return "symbol" == $(t) ? t : t + ""
    }(t)) in e ? Object.defineProperty(e, t, {
        value: r,
        enumerable: !0,
        configurable: !0,
        writable: !0
    }) : e[t] = r, e
}

function Q(e, t) {
    if (null == e) return {};
    var r, n, i = function(e, t) {
        if (null == e) return {};
        var r = {};
        for (var n in e)
            if ({}.hasOwnProperty.call(e, n)) {
                if (-1 !== t.indexOf(n)) continue;
                r[n] = e[n]
            } return r
    }(e, t);
    if (Object.getOwnPropertySymbols) {
        var o = Object.getOwnPropertySymbols(e);
        for (n = 0; n < o.length; n++) r = o[n], -1 === t.indexOf(r) && {}.propertyIsEnumerable.call(e, r) && (i[r] = e[r])
    }
    return i
}
const X = 1e4,
    ee = 1e3,
    te = 3,
    re = "ANTI_SDK_WB_START_TIME";

function ne(e, t) {
    var r = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
        var n = Object.getOwnPropertySymbols(e);
        t && (n = n.filter(function(t) {
            return Object.getOwnPropertyDescriptor(e, t).enumerable
        })), r.push.apply(r, n)
    }
    return r
}

function ie(e) {
    for (var t = 1; t < arguments.length; t++) {
        var r = null != arguments[t] ? arguments[t] : {};
        t % 2 ? ne(Object(r), !0).forEach(function(t) {
            J(e, t, r[t])
        }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(r)) : ne(Object(r)).forEach(function(t) {
            Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(r, t))
        })
    }
    return e
}
const oe = async (e, t = {}, r) => {
    const n = {
        url: e
    };
    n.ctrl = se(r);
    const i = ie(ie({}, t), n.ctrl.controller && {
            signal: n.ctrl.controller.signal
        }),
        o = fetch(e, i),
        s = new Promise((t, i) => {
            n.ctrl.timeoutId = setTimeout(() => {
                var t;
                n.ctrl.timedOut = !0;
                const o = new Error("Request to ".concat(e, " was aborted by timeout in ").concat(r, " ms"));
                o.name = "FetchTimeoutError", n.error = o, "function" == typeof(null === (t = n.ctrl.controller) || void 0 === t ? void 0 : t.abort) ? n.ctrl.controller.abort(o.message) : i(o)
            }, r)
        });
    try {
        var a;
        const e = await Promise.race([o, s]);
        n.answer = e, n.error = null !== (a = n.error) && void 0 !== a ? a : null
    } catch (c) {
        n.error = c, n.answer = null
    } finally {
        n.ctrl.cleanup()
    }
    return n
}, se = e => {
    const t = {
        controller: "function" == typeof AbortController ? new AbortController : null,
        timedOut: !1,
        cleanup: () => null,
        timeoutId: void 0,
        timeoutMs: e
    };
    return t.cleanup = () => clearTimeout(t.timeoutId), t
};
class ae extends Error {
    constructor(e, t) {
        super(t), this.challenge = e, this.name = this.constructor.name, Object.setPrototypeOf(this, ae.prototype)
    }
}
class ce extends Error {
    constructor(e) {
        super(e.message), this.context = e.context, this.code = e.code, this.name = this.constructor.name, Object.setPrototypeOf(this, ce.prototype), ("cause" in Error.prototype || e.cause) && (this.cause = e.cause)
    }
}
var le = (e => (e.FETCH_TIMEOUT = "FETCH_TIMEOUT", e.FETCH_FAILED = "FETCH_FAILED", e.HTTP_ERROR = "HTTP_ERROR", e.PARSE_ERROR = "PARSE_ERROR", e))(le || {});

function de(e) {
    var t, r, n, i;
    if (!e) return "none";
    const o = e;
    return ["type-".concat(Object.prototype.toString.call(e)), "name-".concat(null !== (t = null == o ? void 0 : o.name) && void 0 !== t ? t : ""), "message-".concat(null !== (r = null == o ? void 0 : o.message) && void 0 !== r ? r : ""), "code-".concat(null !== (n = null == o ? void 0 : o.code) && void 0 !== n ? n : ""), "stack-".concat(null !== (i = null == o ? void 0 : o.stack) && void 0 !== i ? i : ""), "string-".concat(String(e))].join("::")
}
const ue = (e, t = 500) => e.length > t ? "".concat(e.slice(0, t), "...[truncated]") : e;

function he(e, t, r) {
    return ["Error during parsing backend response", "status=".concat(e.status), "statusText=".concat(e.statusText), "contentType=".concat(t || "empty"), "bodyPreview=".concat(ue(r))].join("::")
}
const pe = async (e, t) => {
    const {
        answer: r,
        ctrl: n,
        error: i,
        url: o
    } = e;
    if (n.timedOut) {
        const e = de(i);
        throw new ce({
            code: le.FETCH_TIMEOUT,
            message: "Request to ".concat(o, " was aborted by ").concat(n.timeoutMs, " timeout. Details: ").concat(e, "."),
            context: t,
            cause: i
        })
    }
    if (!r) {
        const e = de(i);
        throw new ce({
            code: le.FETCH_FAILED,
            message: "Request to ".concat(o, " was failed. Details: ").concat(e, "."),
            context: t,
            cause: i
        })
    }
    const {
        status: s
    } = r;
    if (498 === s) {
        const {
            challenge: e
        } = await r.json();
        throw new ae(e, "Request to solve next challenge")
    }
    const {
        value: a,
        kind: c,
        rawText: l
    } = await async function(e, t) {
        const r = e.headers.get("content-type") || "",
            n = await e.text();
        try {
            if (r.includes("application/json")) return {
                kind: "json",
                value: JSON.parse(n),
                rawText: n
            }
        } catch (i) {
            throw new ce({
                code: le.PARSE_ERROR,
                message: he(e, r, n),
                context: t,
                cause: i
            })
        }
        return {
            kind: "text",
            value: n,
            rawText: n
        }
    }(r, t), d = String(s).startsWith("2"), u = "json" === c;
    if (!u) throw new ce({
        code: le.PARSE_ERROR,
        message: "Failed to parse body from ".concat(o, ". Details: ").concat(he(r, c, l)),
        context: t
    });
    if (!d && u) {
        const {
            code: e,
            message: r
        } = a;
        throw new ce({
            code: le.HTTP_ERROR,
            message: "Failed request to ".concat(o, ". Message: ").concat(r, ". Status: ").concat(e),
            context: t
        })
    }
    return a
};

function ge(e, t) {
    var r = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
        var n = Object.getOwnPropertySymbols(e);
        t && (n = n.filter(function(t) {
            return Object.getOwnPropertyDescriptor(e, t).enumerable
        })), r.push.apply(r, n)
    }
    return r
}

function me(e) {
    for (var t = 1; t < arguments.length; t++) {
        var r = null != arguments[t] ? arguments[t] : {};
        t % 2 ? ge(Object(r), !0).forEach(function(t) {
            J(e, t, r[t])
        }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(r)) : ge(Object(r)).forEach(function(t) {
            Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(r, t))
        })
    }
    return e
}

function be(e) {
    const t = (new TextEncoder).encode(e),
        r = [];
    for (let n = 0; n < t.length; n += 1) r.push(t[n]);
    return r
}
const fe = e => {
        let t = 0;
        for (let r = 0, n = e.length; r < n; r++) t = (t << 5) - t + e.charCodeAt(r), t |= 0;
        return String(Math.abs(t))
    },
    ye = {
        AmazonBot: "amazonbot",
        "Amazon Silk": "amazon_silk",
        "Android Browser": "android",
        BaiduSpider: "baiduspider",
        Bada: "bada",
        BingCrawler: "bingcrawler",
        Brave: "brave",
        BlackBerry: "blackberry",
        "ChatGPT-User": "chatgpt_user",
        Chrome: "chrome",
        ClaudeBot: "claudebot",
        Chromium: "chromium",
        Diffbot: "diffbot",
        DuckDuckBot: "duckduckbot",
        DuckDuckGo: "duckduckgo",
        Electron: "electron",
        Epiphany: "epiphany",
        FacebookExternalHit: "facebookexternalhit",
        Firefox: "firefox",
        Focus: "focus",
        Generic: "generic",
        "Google Search": "google_search",
        Googlebot: "googlebot",
        GPTBot: "gptbot",
        "Internet Explorer": "ie",
        InternetArchiveCrawler: "internetarchivecrawler",
        "K-Meleon": "k_meleon",
        LibreWolf: "librewolf",
        Linespider: "linespider",
        Maxthon: "maxthon",
        "Meta-ExternalAds": "meta_externalads",
        "Meta-ExternalAgent": "meta_externalagent",
        "Meta-ExternalFetcher": "meta_externalfetcher",
        "Meta-WebIndexer": "meta_webindexer",
        "Microsoft Edge": "edge",
        "MZ Browser": "mz",
        "NAVER Whale Browser": "naver",
        "OAI-SearchBot": "oai_searchbot",
        Omgilibot: "omgilibot",
        Opera: "opera",
        "Opera Coast": "opera_coast",
        "Pale Moon": "pale_moon",
        PerplexityBot: "perplexitybot",
        "Perplexity-User": "perplexity_user",
        PhantomJS: "phantomjs",
        PingdomBot: "pingdombot",
        Puffin: "puffin",
        QQ: "qq",
        QQLite: "qqlite",
        QupZilla: "qupzilla",
        Roku: "roku",
        Safari: "safari",
        Sailfish: "sailfish",
        "Samsung Internet for Android": "samsung_internet",
        SlackBot: "slackbot",
        SeaMonkey: "seamonkey",
        Sleipnir: "sleipnir",
        "Sogou Browser": "sogou",
        Swing: "swing",
        Tizen: "tizen",
        "UC Browser": "uc",
        Vivaldi: "vivaldi",
        "WebOS Browser": "webos",
        WeChat: "wechat",
        YahooSlurp: "yahooslurp",
        "Yandex Browser": "yandex",
        YandexBot: "yandexbot",
        YouBot: "youbot"
    },
    ve = {
        amazonbot: "AmazonBot",
        amazon_silk: "Amazon Silk",
        android: "Android Browser",
        baiduspider: "BaiduSpider",
        bada: "Bada",
        bingcrawler: "BingCrawler",
        blackberry: "BlackBerry",
        brave: "Brave",
        chatgpt_user: "ChatGPT-User",
        chrome: "Chrome",
        claudebot: "ClaudeBot",
        chromium: "Chromium",
        diffbot: "Diffbot",
        duckduckbot: "DuckDuckBot",
        duckduckgo: "DuckDuckGo",
        edge: "Microsoft Edge",
        electron: "Electron",
        epiphany: "Epiphany",
        facebookexternalhit: "FacebookExternalHit",
        firefox: "Firefox",
        focus: "Focus",
        generic: "Generic",
        google_search: "Google Search",
        googlebot: "Googlebot",
        gptbot: "GPTBot",
        ie: "Internet Explorer",
        internetarchivecrawler: "InternetArchiveCrawler",
        k_meleon: "K-Meleon",
        librewolf: "LibreWolf",
        linespider: "Linespider",
        maxthon: "Maxthon",
        meta_externalads: "Meta-ExternalAds",
        meta_externalagent: "Meta-ExternalAgent",
        meta_externalfetcher: "Meta-ExternalFetcher",
        meta_webindexer: "Meta-WebIndexer",
        mz: "MZ Browser",
        naver: "NAVER Whale Browser",
        oai_searchbot: "OAI-SearchBot",
        omgilibot: "Omgilibot",
        opera: "Opera",
        opera_coast: "Opera Coast",
        pale_moon: "Pale Moon",
        perplexitybot: "PerplexityBot",
        perplexity_user: "Perplexity-User",
        phantomjs: "PhantomJS",
        pingdombot: "PingdomBot",
        puffin: "Puffin",
        qq: "QQ Browser",
        qqlite: "QQ Browser Lite",
        qupzilla: "QupZilla",
        roku: "Roku",
        safari: "Safari",
        sailfish: "Sailfish",
        samsung_internet: "Samsung Internet for Android",
        seamonkey: "SeaMonkey",
        slackbot: "SlackBot",
        sleipnir: "Sleipnir",
        sogou: "Sogou Browser",
        swing: "Swing",
        tizen: "Tizen",
        uc: "UC Browser",
        vivaldi: "Vivaldi",
        webos: "WebOS Browser",
        wechat: "WeChat",
        yahooslurp: "YahooSlurp",
        yandex: "Yandex Browser",
        yandexbot: "YandexBot",
        youbot: "YouBot"
    },
    we = {
        bot: "bot",
        desktop: "desktop",
        mobile: "mobile",
        tablet: "tablet",
        tv: "tv"
    },
    Se = {
        Android: "Android",
        Bada: "Bada",
        BlackBerry: "BlackBerry",
        ChromeOS: "Chrome OS",
        HarmonyOS: "HarmonyOS",
        iOS: "iOS",
        Linux: "Linux",
        MacOS: "macOS",
        PlayStation4: "PlayStation 4",
        Roku: "Roku",
        Tizen: "Tizen",
        WebOS: "WebOS",
        Windows: "Windows",
        WindowsPhone: "Windows Phone"
    },
    ke = {
        Blink: "Blink",
        EdgeHTML: "EdgeHTML",
        Gecko: "Gecko",
        Presto: "Presto",
        Trident: "Trident",
        WebKit: "WebKit"
    };
class Oe {
    static getFirstMatch(e, t) {
        const r = t.match(e);
        return r && r.length > 0 && r[1] || ""
    }
    static getSecondMatch(e, t) {
        const r = t.match(e);
        return r && r.length > 1 && r[2] || ""
    }
    static matchAndReturnConst(e, t, r) {
        if (e.test(t)) return r
    }
    static getWindowsVersionName(e) {
        switch (e) {
            case "NT":
                return "NT";
            case "XP":
            case "NT 5.1":
                return "XP";
            case "NT 5.0":
                return "2000";
            case "NT 5.2":
                return "2003";
            case "NT 6.0":
                return "Vista";
            case "NT 6.1":
                return "7";
            case "NT 6.2":
                return "8";
            case "NT 6.3":
                return "8.1";
            case "NT 10.0":
                return "10";
            default:
                return
        }
    }
    static getMacOSVersionName(e) {
        const t = e.split(".").splice(0, 2).map(e => parseInt(e, 10) || 0);
        t.push(0);
        const r = t[0],
            n = t[1];
        if (10 === r) switch (n) {
            case 5:
                return "Leopard";
            case 6:
                return "Snow Leopard";
            case 7:
                return "Lion";
            case 8:
                return "Mountain Lion";
            case 9:
                return "Mavericks";
            case 10:
                return "Yosemite";
            case 11:
                return "El Capitan";
            case 12:
                return "Sierra";
            case 13:
                return "High Sierra";
            case 14:
                return "Mojave";
            case 15:
                return "Catalina";
            default:
                return
        }
        switch (r) {
            case 11:
                return "Big Sur";
            case 12:
                return "Monterey";
            case 13:
                return "Ventura";
            case 14:
                return "Sonoma";
            case 15:
                return "Sequoia";
            default:
                return
        }
    }
    static getAndroidVersionName(e) {
        const t = e.split(".").splice(0, 2).map(e => parseInt(e, 10) || 0);
        if (t.push(0), !(1 === t[0] && t[1] < 5)) return 1 === t[0] && t[1] < 6 ? "Cupcake" : 1 === t[0] && t[1] >= 6 ? "Donut" : 2 === t[0] && t[1] < 2 ? "Eclair" : 2 === t[0] && 2 === t[1] ? "Froyo" : 2 === t[0] && t[1] > 2 ? "Gingerbread" : 3 === t[0] ? "Honeycomb" : 4 === t[0] && t[1] < 1 ? "Ice Cream Sandwich" : 4 === t[0] && t[1] < 4 ? "Jelly Bean" : 4 === t[0] && t[1] >= 4 ? "KitKat" : 5 === t[0] ? "Lollipop" : 6 === t[0] ? "Marshmallow" : 7 === t[0] ? "Nougat" : 8 === t[0] ? "Oreo" : 9 === t[0] ? "Pie" : void 0
    }
    static getVersionPrecision(e) {
        return e.split(".").length
    }
    static compareVersions(e, t, r = !1) {
        const n = Oe.getVersionPrecision(e),
            i = Oe.getVersionPrecision(t);
        let o = Math.max(n, i),
            s = 0;
        const a = Oe.map([e, t], e => {
            const t = o - Oe.getVersionPrecision(e),
                r = e + new Array(t + 1).join(".0");
            return Oe.map(r.split("."), e => new Array(20 - e.length).join("0") + e).reverse()
        });
        for (r && (s = o - Math.min(n, i)), o -= 1; o >= s;) {
            if (a[0][o] > a[1][o]) return 1;
            if (a[0][o] === a[1][o]) {
                if (o === s) return 0;
                o -= 1
            } else if (a[0][o] < a[1][o]) return -1
        }
    }
    static map(e, t) {
        const r = [];
        let n;
        if (Array.prototype.map) return Array.prototype.map.call(e, t);
        for (n = 0; n < e.length; n += 1) r.push(t(e[n]));
        return r
    }
    static find(e, t) {
        let r, n;
        if (Array.prototype.find) return Array.prototype.find.call(e, t);
        for (r = 0, n = e.length; r < n; r += 1) {
            const n = e[r];
            if (t(n, r)) return n
        }
    }
    static assign(e, ...t) {
        const r = e;
        let n, i;
        if (Object.assign) return Object.assign(e, ...t);
        for (n = 0, i = t.length; n < i; n += 1) {
            const e = t[n];
            "object" == typeof e && null !== e && Object.keys(e).forEach(t => {
                r[t] = e[t]
            })
        }
        return e
    }
    static getBrowserAlias(e) {
        return ye[e]
    }
    static getBrowserTypeByAlias(e) {
        return ve[e] || ""
    }
}
const Me = /version\/(\d+(\.?_?\d+)+)/i,
    xe = [{
        test: [/gptbot/i],
        describe(e) {
            const t = {
                    name: "GPTBot"
                },
                r = Oe.getFirstMatch(/gptbot\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/chatgpt-user/i],
        describe(e) {
            const t = {
                    name: "ChatGPT-User"
                },
                r = Oe.getFirstMatch(/chatgpt-user\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/oai-searchbot/i],
        describe(e) {
            const t = {
                    name: "OAI-SearchBot"
                },
                r = Oe.getFirstMatch(/oai-searchbot\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/claudebot/i, /claude-web/i, /claude-user/i, /claude-searchbot/i],
        describe(e) {
            const t = {
                    name: "ClaudeBot"
                },
                r = Oe.getFirstMatch(/(?:claudebot|claude-web|claude-user|claude-searchbot)\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/omgilibot/i, /webzio-extended/i],
        describe(e) {
            const t = {
                    name: "Omgilibot"
                },
                r = Oe.getFirstMatch(/(?:omgilibot|webzio-extended)\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/diffbot/i],
        describe(e) {
            const t = {
                    name: "Diffbot"
                },
                r = Oe.getFirstMatch(/diffbot\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/perplexitybot/i],
        describe(e) {
            const t = {
                    name: "PerplexityBot"
                },
                r = Oe.getFirstMatch(/perplexitybot\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/perplexity-user/i],
        describe(e) {
            const t = {
                    name: "Perplexity-User"
                },
                r = Oe.getFirstMatch(/perplexity-user\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/youbot/i],
        describe(e) {
            const t = {
                    name: "YouBot"
                },
                r = Oe.getFirstMatch(/youbot\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/meta-webindexer/i],
        describe(e) {
            const t = {
                    name: "Meta-WebIndexer"
                },
                r = Oe.getFirstMatch(/meta-webindexer\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/meta-externalads/i],
        describe(e) {
            const t = {
                    name: "Meta-ExternalAds"
                },
                r = Oe.getFirstMatch(/meta-externalads\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/meta-externalagent/i],
        describe(e) {
            const t = {
                    name: "Meta-ExternalAgent"
                },
                r = Oe.getFirstMatch(/meta-externalagent\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/meta-externalfetcher/i],
        describe(e) {
            const t = {
                    name: "Meta-ExternalFetcher"
                },
                r = Oe.getFirstMatch(/meta-externalfetcher\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/googlebot/i],
        describe(e) {
            const t = {
                    name: "Googlebot"
                },
                r = Oe.getFirstMatch(/googlebot\/(\d+(\.\d+))/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/linespider/i],
        describe(e) {
            const t = {
                    name: "Linespider"
                },
                r = Oe.getFirstMatch(/(?:linespider)(?:-[-\w]+)?[\s/](\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/amazonbot/i],
        describe(e) {
            const t = {
                    name: "AmazonBot"
                },
                r = Oe.getFirstMatch(/amazonbot\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/bingbot/i],
        describe(e) {
            const t = {
                    name: "BingCrawler"
                },
                r = Oe.getFirstMatch(/bingbot\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/baiduspider/i],
        describe(e) {
            const t = {
                    name: "BaiduSpider"
                },
                r = Oe.getFirstMatch(/baiduspider\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/duckduckbot/i],
        describe(e) {
            const t = {
                    name: "DuckDuckBot"
                },
                r = Oe.getFirstMatch(/duckduckbot\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/ia_archiver/i],
        describe(e) {
            const t = {
                    name: "InternetArchiveCrawler"
                },
                r = Oe.getFirstMatch(/ia_archiver\/(\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/facebookexternalhit/i, /facebookcatalog/i],
        describe: () => ({
            name: "FacebookExternalHit"
        })
    }, {
        test: [/slackbot/i, /slack-imgProxy/i],
        describe(e) {
            const t = {
                    name: "SlackBot"
                },
                r = Oe.getFirstMatch(/(?:slackbot|slack-imgproxy)(?:-[-\w]+)?[\s/](\d+(\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/yahoo!?[\s/]*slurp/i],
        describe: () => ({
            name: "YahooSlurp"
        })
    }, {
        test: [/yandexbot/i, /yandexmobilebot/i],
        describe: () => ({
            name: "YandexBot"
        })
    }, {
        test: [/pingdom/i],
        describe: () => ({
            name: "PingdomBot"
        })
    }, {
        test: [/opera/i],
        describe(e) {
            const t = {
                    name: "Opera"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:opera)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/opr\/|opios/i],
        describe(e) {
            const t = {
                    name: "Opera"
                },
                r = Oe.getFirstMatch(/(?:opr|opios)[\s/](\S+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/SamsungBrowser/i],
        describe(e) {
            const t = {
                    name: "Samsung Internet for Android"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:SamsungBrowser)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/Whale/i],
        describe(e) {
            const t = {
                    name: "NAVER Whale Browser"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:whale)[\s/](\d+(?:\.\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/PaleMoon/i],
        describe(e) {
            const t = {
                    name: "Pale Moon"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:PaleMoon)[\s/](\d+(?:\.\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/MZBrowser/i],
        describe(e) {
            const t = {
                    name: "MZ Browser"
                },
                r = Oe.getFirstMatch(/(?:MZBrowser)[\s/](\d+(?:\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/focus/i],
        describe(e) {
            const t = {
                    name: "Focus"
                },
                r = Oe.getFirstMatch(/(?:focus)[\s/](\d+(?:\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/swing/i],
        describe(e) {
            const t = {
                    name: "Swing"
                },
                r = Oe.getFirstMatch(/(?:swing)[\s/](\d+(?:\.\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/coast/i],
        describe(e) {
            const t = {
                    name: "Opera Coast"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:coast)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/opt\/\d+(?:.?_?\d+)+/i],
        describe(e) {
            const t = {
                    name: "Opera Touch"
                },
                r = Oe.getFirstMatch(/(?:opt)[\s/](\d+(\.?_?\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/yabrowser/i],
        describe(e) {
            const t = {
                    name: "Yandex Browser"
                },
                r = Oe.getFirstMatch(/(?:yabrowser)[\s/](\d+(\.?_?\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/ucbrowser/i],
        describe(e) {
            const t = {
                    name: "UC Browser"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:ucbrowser)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/Maxthon|mxios/i],
        describe(e) {
            const t = {
                    name: "Maxthon"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:Maxthon|mxios)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/epiphany/i],
        describe(e) {
            const t = {
                    name: "Epiphany"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:epiphany)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/puffin/i],
        describe(e) {
            const t = {
                    name: "Puffin"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:puffin)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/sleipnir/i],
        describe(e) {
            const t = {
                    name: "Sleipnir"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:sleipnir)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/k-meleon/i],
        describe(e) {
            const t = {
                    name: "K-Meleon"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/(?:k-meleon)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/micromessenger/i],
        describe(e) {
            const t = {
                    name: "WeChat"
                },
                r = Oe.getFirstMatch(/(?:micromessenger)[\s/](\d+(\.?_?\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/qqbrowser/i],
        describe(e) {
            const t = {
                    name: /qqbrowserlite/i.test(e) ? "QQ Browser Lite" : "QQ Browser"
                },
                r = Oe.getFirstMatch(/(?:qqbrowserlite|qqbrowser)[/](\d+(\.?_?\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/msie|trident/i],
        describe(e) {
            const t = {
                    name: "Internet Explorer"
                },
                r = Oe.getFirstMatch(/(?:msie |rv:)(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/\sedg\//i],
        describe(e) {
            const t = {
                    name: "Microsoft Edge"
                },
                r = Oe.getFirstMatch(/\sedg\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/edg([ea]|ios)/i],
        describe(e) {
            const t = {
                    name: "Microsoft Edge"
                },
                r = Oe.getSecondMatch(/edg([ea]|ios)\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/vivaldi/i],
        describe(e) {
            const t = {
                    name: "Vivaldi"
                },
                r = Oe.getFirstMatch(/vivaldi\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/seamonkey/i],
        describe(e) {
            const t = {
                    name: "SeaMonkey"
                },
                r = Oe.getFirstMatch(/seamonkey\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/sailfish/i],
        describe(e) {
            const t = {
                    name: "Sailfish"
                },
                r = Oe.getFirstMatch(/sailfish\s?browser\/(\d+(\.\d+)?)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/silk/i],
        describe(e) {
            const t = {
                    name: "Amazon Silk"
                },
                r = Oe.getFirstMatch(/silk\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/phantom/i],
        describe(e) {
            const t = {
                    name: "PhantomJS"
                },
                r = Oe.getFirstMatch(/phantomjs\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/slimerjs/i],
        describe(e) {
            const t = {
                    name: "SlimerJS"
                },
                r = Oe.getFirstMatch(/slimerjs\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/blackberry|\bbb\d+/i, /rim\stablet/i],
        describe(e) {
            const t = {
                    name: "BlackBerry"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/blackberry[\d]+\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/(web|hpw)[o0]s/i],
        describe(e) {
            const t = {
                    name: "WebOS Browser"
                },
                r = Oe.getFirstMatch(Me, e) || Oe.getFirstMatch(/w(?:eb)?[o0]sbrowser\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/bada/i],
        describe(e) {
            const t = {
                    name: "Bada"
                },
                r = Oe.getFirstMatch(/dolfin\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/tizen/i],
        describe(e) {
            const t = {
                    name: "Tizen"
                },
                r = Oe.getFirstMatch(/(?:tizen\s?)?browser\/(\d+(\.?_?\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/qupzilla/i],
        describe(e) {
            const t = {
                    name: "QupZilla"
                },
                r = Oe.getFirstMatch(/(?:qupzilla)[\s/](\d+(\.?_?\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/librewolf/i],
        describe(e) {
            const t = {
                    name: "LibreWolf"
                },
                r = Oe.getFirstMatch(/(?:librewolf)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/firefox|iceweasel|fxios/i],
        describe(e) {
            const t = {
                    name: "Firefox"
                },
                r = Oe.getFirstMatch(/(?:firefox|iceweasel|fxios)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/electron/i],
        describe(e) {
            const t = {
                    name: "Electron"
                },
                r = Oe.getFirstMatch(/(?:electron)\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/sogoumobilebrowser/i, /metasr/i, /se 2\.[x]/i],
        describe(e) {
            const t = {
                    name: "Sogou Browser"
                },
                r = Oe.getFirstMatch(/(?:sogoumobilebrowser)[\s/](\d+(\.?_?\d+)+)/i, e),
                n = Oe.getFirstMatch(/(?:chrome|crios|crmo)\/(\d+(\.?_?\d+)+)/i, e),
                i = Oe.getFirstMatch(/se ([\d.]+)x/i, e),
                o = r || n || i;
            return o && (t.version = o), t
        }
    }, {
        test: [/MiuiBrowser/i],
        describe(e) {
            const t = {
                    name: "Miui"
                },
                r = Oe.getFirstMatch(/(?:MiuiBrowser)[\s/](\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: e => !!e.hasBrand("DuckDuckGo") || e.test(/\sDdg\/[\d.]+$/i),
        describe(e, t) {
            const r = {
                name: "DuckDuckGo"
            };
            if (t) {
                const e = t.getBrandVersion("DuckDuckGo");
                if (e) return r.version = e, r
            }
            const n = Oe.getFirstMatch(/\sDdg\/([\d.]+)$/i, e);
            return n && (r.version = n), r
        }
    }, {
        test: e => e.hasBrand("Brave"),
        describe(e, t) {
            const r = {
                name: "Brave"
            };
            if (t) {
                const e = t.getBrandVersion("Brave");
                if (e) return r.version = e, r
            }
            return r
        }
    }, {
        test: [/chromium/i],
        describe(e) {
            const t = {
                    name: "Chromium"
                },
                r = Oe.getFirstMatch(/(?:chromium)[\s/](\d+(\.?_?\d+)+)/i, e) || Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/chrome|crios|crmo/i],
        describe(e) {
            const t = {
                    name: "Chrome"
                },
                r = Oe.getFirstMatch(/(?:chrome|crios|crmo)\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/GSA/i],
        describe(e) {
            const t = {
                    name: "Google Search"
                },
                r = Oe.getFirstMatch(/(?:GSA)\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test(e) {
            const t = !e.test(/like android/i),
                r = e.test(/android/i);
            return t && r
        },
        describe(e) {
            const t = {
                    name: "Android Browser"
                },
                r = Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/playstation 4/i],
        describe(e) {
            const t = {
                    name: "PlayStation 4"
                },
                r = Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/safari|applewebkit/i],
        describe(e) {
            const t = {
                    name: "Safari"
                },
                r = Oe.getFirstMatch(Me, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/.*/i],
        describe(e) {
            const t = -1 !== e.search("\\(") ? /^(.*)\/(.*)[ \t]\((.*)/ : /^(.*)\/(.*) /;
            return {
                name: Oe.getFirstMatch(t, e),
                version: Oe.getSecondMatch(t, e)
            }
        }
    }],
    Te = [{
        test: [/Roku\/DVP/],
        describe(e) {
            const t = Oe.getFirstMatch(/Roku\/DVP-(\d+\.\d+)/i, e);
            return {
                name: Se.Roku,
                version: t
            }
        }
    }, {
        test: [/windows phone/i],
        describe(e) {
            const t = Oe.getFirstMatch(/windows phone (?:os)?\s?(\d+(\.\d+)*)/i, e);
            return {
                name: Se.WindowsPhone,
                version: t
            }
        }
    }, {
        test: [/windows /i],
        describe(e) {
            const t = Oe.getFirstMatch(/Windows ((NT|XP)( \d\d?.\d)?)/i, e),
                r = Oe.getWindowsVersionName(t);
            return {
                name: Se.Windows,
                version: t,
                versionName: r
            }
        }
    }, {
        test: [/Macintosh(.*?) FxiOS(.*?)\//],
        describe(e) {
            const t = {
                    name: Se.iOS
                },
                r = Oe.getSecondMatch(/(Version\/)(\d[\d.]+)/, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/macintosh/i],
        describe(e) {
            const t = Oe.getFirstMatch(/mac os x (\d+(\.?_?\d+)+)/i, e).replace(/[_\s]/g, "."),
                r = Oe.getMacOSVersionName(t),
                n = {
                    name: Se.MacOS,
                    version: t
                };
            return r && (n.versionName = r), n
        }
    }, {
        test: [/(ipod|iphone|ipad)/i],
        describe(e) {
            const t = Oe.getFirstMatch(/os (\d+([_\s]\d+)*) like mac os x/i, e).replace(/[_\s]/g, ".");
            return {
                name: Se.iOS,
                version: t
            }
        }
    }, {
        test: [/OpenHarmony/i],
        describe(e) {
            const t = Oe.getFirstMatch(/OpenHarmony\s+(\d+(\.\d+)*)/i, e);
            return {
                name: Se.HarmonyOS,
                version: t
            }
        }
    }, {
        test(e) {
            const t = !e.test(/like android/i),
                r = e.test(/android/i);
            return t && r
        },
        describe(e) {
            const t = Oe.getFirstMatch(/android[\s/-](\d+(\.\d+)*)/i, e),
                r = Oe.getAndroidVersionName(t),
                n = {
                    name: Se.Android,
                    version: t
                };
            return r && (n.versionName = r), n
        }
    }, {
        test: [/(web|hpw)[o0]s/i],
        describe(e) {
            const t = Oe.getFirstMatch(/(?:web|hpw)[o0]s\/(\d+(\.\d+)*)/i, e),
                r = {
                    name: Se.WebOS
                };
            return t && t.length && (r.version = t), r
        }
    }, {
        test: [/blackberry|\bbb\d+/i, /rim\stablet/i],
        describe(e) {
            const t = Oe.getFirstMatch(/rim\stablet\sos\s(\d+(\.\d+)*)/i, e) || Oe.getFirstMatch(/blackberry\d+\/(\d+([_\s]\d+)*)/i, e) || Oe.getFirstMatch(/\bbb(\d+)/i, e);
            return {
                name: Se.BlackBerry,
                version: t
            }
        }
    }, {
        test: [/bada/i],
        describe(e) {
            const t = Oe.getFirstMatch(/bada\/(\d+(\.\d+)*)/i, e);
            return {
                name: Se.Bada,
                version: t
            }
        }
    }, {
        test: [/tizen/i],
        describe(e) {
            const t = Oe.getFirstMatch(/tizen[/\s](\d+(\.\d+)*)/i, e);
            return {
                name: Se.Tizen,
                version: t
            }
        }
    }, {
        test: [/linux/i],
        describe: () => ({
            name: Se.Linux
        })
    }, {
        test: [/CrOS/],
        describe: () => ({
            name: Se.ChromeOS
        })
    }, {
        test: [/PlayStation 4/],
        describe(e) {
            const t = Oe.getFirstMatch(/PlayStation 4[/\s](\d+(\.\d+)*)/i, e);
            return {
                name: Se.PlayStation4,
                version: t
            }
        }
    }],
    Ee = [{
        test: [/googlebot/i],
        describe: () => ({
            type: we.bot,
            vendor: "Google"
        })
    }, {
        test: [/linespider/i],
        describe: () => ({
            type: we.bot,
            vendor: "Line"
        })
    }, {
        test: [/amazonbot/i],
        describe: () => ({
            type: we.bot,
            vendor: "Amazon"
        })
    }, {
        test: [/gptbot/i],
        describe: () => ({
            type: we.bot,
            vendor: "OpenAI"
        })
    }, {
        test: [/chatgpt-user/i],
        describe: () => ({
            type: we.bot,
            vendor: "OpenAI"
        })
    }, {
        test: [/oai-searchbot/i],
        describe: () => ({
            type: we.bot,
            vendor: "OpenAI"
        })
    }, {
        test: [/baiduspider/i],
        describe: () => ({
            type: we.bot,
            vendor: "Baidu"
        })
    }, {
        test: [/bingbot/i],
        describe: () => ({
            type: we.bot,
            vendor: "Bing"
        })
    }, {
        test: [/duckduckbot/i],
        describe: () => ({
            type: we.bot,
            vendor: "DuckDuckGo"
        })
    }, {
        test: [/claudebot/i, /claude-web/i, /claude-user/i, /claude-searchbot/i],
        describe: () => ({
            type: we.bot,
            vendor: "Anthropic"
        })
    }, {
        test: [/omgilibot/i, /webzio-extended/i],
        describe: () => ({
            type: we.bot,
            vendor: "Webz.io"
        })
    }, {
        test: [/diffbot/i],
        describe: () => ({
            type: we.bot,
            vendor: "Diffbot"
        })
    }, {
        test: [/perplexitybot/i],
        describe: () => ({
            type: we.bot,
            vendor: "Perplexity AI"
        })
    }, {
        test: [/perplexity-user/i],
        describe: () => ({
            type: we.bot,
            vendor: "Perplexity AI"
        })
    }, {
        test: [/youbot/i],
        describe: () => ({
            type: we.bot,
            vendor: "You.com"
        })
    }, {
        test: [/ia_archiver/i],
        describe: () => ({
            type: we.bot,
            vendor: "Internet Archive"
        })
    }, {
        test: [/meta-webindexer/i],
        describe: () => ({
            type: we.bot,
            vendor: "Meta"
        })
    }, {
        test: [/meta-externalads/i],
        describe: () => ({
            type: we.bot,
            vendor: "Meta"
        })
    }, {
        test: [/meta-externalagent/i],
        describe: () => ({
            type: we.bot,
            vendor: "Meta"
        })
    }, {
        test: [/meta-externalfetcher/i],
        describe: () => ({
            type: we.bot,
            vendor: "Meta"
        })
    }, {
        test: [/facebookexternalhit/i, /facebookcatalog/i],
        describe: () => ({
            type: we.bot,
            vendor: "Meta"
        })
    }, {
        test: [/slackbot/i, /slack-imgProxy/i],
        describe: () => ({
            type: we.bot,
            vendor: "Slack"
        })
    }, {
        test: [/yahoo/i],
        describe: () => ({
            type: we.bot,
            vendor: "Yahoo"
        })
    }, {
        test: [/yandexbot/i, /yandexmobilebot/i],
        describe: () => ({
            type: we.bot,
            vendor: "Yandex"
        })
    }, {
        test: [/pingdom/i],
        describe: () => ({
            type: we.bot,
            vendor: "Pingdom"
        })
    }, {
        test: [/huawei/i],
        describe(e) {
            const t = Oe.getFirstMatch(/(can-l01)/i, e) && "Nova",
                r = {
                    type: we.mobile,
                    vendor: "Huawei"
                };
            return t && (r.model = t), r
        }
    }, {
        test: [/nexus\s*(?:7|8|9|10).*/i],
        describe: () => ({
            type: we.tablet,
            vendor: "Nexus"
        })
    }, {
        test: [/ipad/i],
        describe: () => ({
            type: we.tablet,
            vendor: "Apple",
            model: "iPad"
        })
    }, {
        test: [/Macintosh(.*?) FxiOS(.*?)\//],
        describe: () => ({
            type: we.tablet,
            vendor: "Apple",
            model: "iPad"
        })
    }, {
        test: [/kftt build/i],
        describe: () => ({
            type: we.tablet,
            vendor: "Amazon",
            model: "Kindle Fire HD 7"
        })
    }, {
        test: [/silk/i],
        describe: () => ({
            type: we.tablet,
            vendor: "Amazon"
        })
    }, {
        test: [/tablet(?! pc)/i],
        describe: () => ({
            type: we.tablet
        })
    }, {
        test(e) {
            const t = e.test(/ipod|iphone/i),
                r = e.test(/like (ipod|iphone)/i);
            return t && !r
        },
        describe(e) {
            const t = Oe.getFirstMatch(/(ipod|iphone)/i, e);
            return {
                type: we.mobile,
                vendor: "Apple",
                model: t
            }
        }
    }, {
        test: [/nexus\s*[0-6].*/i, /galaxy nexus/i],
        describe: () => ({
            type: we.mobile,
            vendor: "Nexus"
        })
    }, {
        test: [/Nokia/i],
        describe(e) {
            const t = Oe.getFirstMatch(/Nokia\s+([0-9]+(\.[0-9]+)?)/i, e),
                r = {
                    type: we.mobile,
                    vendor: "Nokia"
                };
            return t && (r.model = t), r
        }
    }, {
        test: [/[^-]mobi/i],
        describe: () => ({
            type: we.mobile
        })
    }, {
        test: e => "blackberry" === e.getBrowserName(!0),
        describe: () => ({
            type: we.mobile,
            vendor: "BlackBerry"
        })
    }, {
        test: e => "bada" === e.getBrowserName(!0),
        describe: () => ({
            type: we.mobile
        })
    }, {
        test: e => "windows phone" === e.getBrowserName(),
        describe: () => ({
            type: we.mobile,
            vendor: "Microsoft"
        })
    }, {
        test(e) {
            const t = Number(String(e.getOSVersion()).split(".")[0]);
            return "android" === e.getOSName(!0) && t >= 3
        },
        describe: () => ({
            type: we.tablet
        })
    }, {
        test: e => "android" === e.getOSName(!0),
        describe: () => ({
            type: we.mobile
        })
    }, {
        test: [/smart-?tv|smarttv/i],
        describe: () => ({
            type: we.tv
        })
    }, {
        test: [/netcast/i],
        describe: () => ({
            type: we.tv
        })
    }, {
        test: e => "macos" === e.getOSName(!0),
        describe: () => ({
            type: we.desktop,
            vendor: "Apple"
        })
    }, {
        test: e => "windows" === e.getOSName(!0),
        describe: () => ({
            type: we.desktop
        })
    }, {
        test: e => "linux" === e.getOSName(!0),
        describe: () => ({
            type: we.desktop
        })
    }, {
        test: e => "playstation 4" === e.getOSName(!0),
        describe: () => ({
            type: we.tv
        })
    }, {
        test: e => "roku" === e.getOSName(!0),
        describe: () => ({
            type: we.tv
        })
    }],
    Fe = [{
        test: e => "microsoft edge" === e.getBrowserName(!0),
        describe(e) {
            if (/\sedg\//i.test(e)) return {
                name: ke.Blink
            };
            const t = Oe.getFirstMatch(/edge\/(\d+(\.?_?\d+)+)/i, e);
            return {
                name: ke.EdgeHTML,
                version: t
            }
        }
    }, {
        test: [/trident/i],
        describe(e) {
            const t = {
                    name: ke.Trident
                },
                r = Oe.getFirstMatch(/trident\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: e => e.test(/presto/i),
        describe(e) {
            const t = {
                    name: ke.Presto
                },
                r = Oe.getFirstMatch(/presto\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test(e) {
            const t = e.test(/gecko/i),
                r = e.test(/like gecko/i);
            return t && !r
        },
        describe(e) {
            const t = {
                    name: ke.Gecko
                },
                r = Oe.getFirstMatch(/gecko\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }, {
        test: [/(apple)?webkit\/537\.36/i],
        describe: () => ({
            name: ke.Blink
        })
    }, {
        test: [/(apple)?webkit/i],
        describe(e) {
            const t = {
                    name: ke.WebKit
                },
                r = Oe.getFirstMatch(/webkit\/(\d+(\.?_?\d+)+)/i, e);
            return r && (t.version = r), t
        }
    }];
class Pe {
    constructor(e, t = !1, r = null) {
        if (null == e || "" === e) throw new Error("UserAgent parameter can't be empty");
        this._ua = e;
        let n = !1;
        "boolean" == typeof t ? (n = t, this._hints = r) : this._hints = null != t && "object" == typeof t ? t : null, this.parsedResult = {}, !0 !== n && this.parse()
    }
    getHints() {
        return this._hints
    }
    hasBrand(e) {
        if (!this._hints || !Array.isArray(this._hints.brands)) return !1;
        const t = e.toLowerCase();
        return this._hints.brands.some(e => e.brand && e.brand.toLowerCase() === t)
    }
    getBrandVersion(e) {
        if (!this._hints || !Array.isArray(this._hints.brands)) return;
        const t = e.toLowerCase(),
            r = this._hints.brands.find(e => e.brand && e.brand.toLowerCase() === t);
        return r ? r.version : void 0
    }
    getUA() {
        return this._ua
    }
    test(e) {
        return e.test(this._ua)
    }
    parseBrowser() {
        this.parsedResult.browser = {};
        const e = Oe.find(xe, e => {
            if ("function" == typeof e.test) return e.test(this);
            if (Array.isArray(e.test)) return e.test.some(e => this.test(e));
            throw new Error("Browser's test function is not valid")
        });
        return e && (this.parsedResult.browser = e.describe(this.getUA(), this)), this.parsedResult.browser
    }
    getBrowser() {
        return this.parsedResult.browser ? this.parsedResult.browser : this.parseBrowser()
    }
    getBrowserName(e) {
        return e ? String(this.getBrowser().name).toLowerCase() || "" : this.getBrowser().name || ""
    }
    getBrowserVersion() {
        return this.getBrowser().version
    }
    getOS() {
        return this.parsedResult.os ? this.parsedResult.os : this.parseOS()
    }
    parseOS() {
        this.parsedResult.os = {};
        const e = Oe.find(Te, e => {
            if ("function" == typeof e.test) return e.test(this);
            if (Array.isArray(e.test)) return e.test.some(e => this.test(e));
            throw new Error("Browser's test function is not valid")
        });
        return e && (this.parsedResult.os = e.describe(this.getUA())), this.parsedResult.os
    }
    getOSName(e) {
        const {
            name: t
        } = this.getOS();
        return e ? String(t).toLowerCase() || "" : t || ""
    }
    getOSVersion() {
        return this.getOS().version
    }
    getPlatform() {
        return this.parsedResult.platform ? this.parsedResult.platform : this.parsePlatform()
    }
    getPlatformType(e = !1) {
        const {
            type: t
        } = this.getPlatform();
        return e ? String(t).toLowerCase() || "" : t || ""
    }
    parsePlatform() {
        this.parsedResult.platform = {};
        const e = Oe.find(Ee, e => {
            if ("function" == typeof e.test) return e.test(this);
            if (Array.isArray(e.test)) return e.test.some(e => this.test(e));
            throw new Error("Browser's test function is not valid")
        });
        return e && (this.parsedResult.platform = e.describe(this.getUA())), this.parsedResult.platform
    }
    getEngine() {
        return this.parsedResult.engine ? this.parsedResult.engine : this.parseEngine()
    }
    getEngineName(e) {
        return e ? String(this.getEngine().name).toLowerCase() || "" : this.getEngine().name || ""
    }
    parseEngine() {
        this.parsedResult.engine = {};
        const e = Oe.find(Fe, e => {
            if ("function" == typeof e.test) return e.test(this);
            if (Array.isArray(e.test)) return e.test.some(e => this.test(e));
            throw new Error("Browser's test function is not valid")
        });
        return e && (this.parsedResult.engine = e.describe(this.getUA())), this.parsedResult.engine
    }
    parse() {
        return this.parseBrowser(), this.parseOS(), this.parsePlatform(), this.parseEngine(), this
    }
    getResult() {
        return Oe.assign({}, this.parsedResult)
    }
    satisfies(e) {
        const t = {};
        let r = 0;
        const n = {};
        let i = 0;
        if (Object.keys(e).forEach(o => {
                const s = e[o];
                "string" == typeof s ? (n[o] = s, i += 1) : "object" == typeof s && (t[o] = s, r += 1)
            }), r > 0) {
            const e = Object.keys(t),
                r = Oe.find(e, e => this.isOS(e));
            if (r) {
                const e = this.satisfies(t[r]);
                if (void 0 !== e) return e
            }
            const n = Oe.find(e, e => this.isPlatform(e));
            if (n) {
                const e = this.satisfies(t[n]);
                if (void 0 !== e) return e
            }
        }
        if (i > 0) {
            const e = Object.keys(n),
                t = Oe.find(e, e => this.isBrowser(e, !0));
            if (void 0 !== t) return this.compareVersion(n[t])
        }
    }
    isBrowser(e, t = !1) {
        const r = this.getBrowserName().toLowerCase();
        let n = e.toLowerCase();
        const i = Oe.getBrowserTypeByAlias(n);
        return t && i && (n = i.toLowerCase()), n === r
    }
    compareVersion(e) {
        let t = [0],
            r = e,
            n = !1;
        const i = this.getBrowserVersion();
        if ("string" == typeof i) return ">" === e[0] || "<" === e[0] ? (r = e.substr(1), "=" === e[1] ? (n = !0, r = e.substr(2)) : t = [], ">" === e[0] ? t.push(1) : t.push(-1)) : "=" === e[0] ? r = e.substr(1) : "~" === e[0] && (n = !0, r = e.substr(1)), t.indexOf(Oe.compareVersions(i, r, n)) > -1
    }
    isOS(e) {
        return this.getOSName(!0) === String(e).toLowerCase()
    }
    isPlatform(e) {
        return this.getPlatformType(!0) === String(e).toLowerCase()
    }
    isEngine(e) {
        return this.getEngineName(!0) === String(e).toLowerCase()
    }
    is(e, t = !1) {
        return this.isBrowser(e, t) || this.isOS(e) || this.isPlatform(e)
    }
    some(e = []) {
        return e.some(e => this.is(e))
    }
}
const Be = class {
        static getParser(e, t = !1, r = null) {
            if ("string" != typeof e) throw new Error("UserAgent should be a string");
            return new Pe(e, t, r)
        }
        static parse(e, t = null) {
            return new Pe(e, t).getResult()
        }
        static get BROWSER_MAP() {
            return ve
        }
        static get ENGINE_MAP() {
            return ke
        }
        static get OS_MAP() {
            return Se
        }
        static get PLATFORMS_MAP() {
            return we
        }
    }.getParser(window.navigator.userAgent),
    Ce = {
        ua: Be.getUA(),
        browser: Be.getBrowserName(),
        browser_v: Be.getBrowserVersion(),
        os: Be.getOSName(),
        os_v: Be.getOSVersion(),
        engine: Be.getEngineName(),
        platform: Be.getPlatformType()
    },
    Ae = /^.*\/(.*)\.js/i,
    _e = async e => {
        const t = function(e) {
                const t = function(e) {
                        const t = e.match(Ae);
                        if (t) return t[1];
                        throw new Error("Cannot match filename from script: ".concat(e))
                    }(e),
                    r = fe(t);
                return window.Symbol.for(r)
            }(e),
            r = await (i = e, new Promise((e, t) => {
                const r = document.createElement("script");
                r.src = i, r.async = !0, r.type = "text/javascript", r.addEventListener("load", () => e(!0)), r.addEventListener("error", e => t(e)), (document.head || document.body).appendChild(r)
            })),
            n = await (async e => (e => {
                const {
                    attempts: t,
                    interval: r,
                    isLoadedCallback: n
                } = e;
                return new Promise((e, i) => {
                    let o = 0,
                        s = window.setInterval(() => {
                            o += 1;
                            const r = n();
                            (r || o === t) && (window.clearInterval(s), s = null, r ? e(!0) : i(new Error("checkApiAttempts error")))
                        }, r)
                })
            })({
                attempts: 3,
                interval: 500,
                isLoadedCallback: () => "function" == typeof window[e]
            }))(t);
        var i;
        if (r && n) return window[t];
        throw new Error("Module was not initialized properly, try again.")
    };

function je(e) {
    try {
        return JSON.stringify(e)
    } catch (t) {
        try {
            return String(e)
        } catch (r) {
            return "[Unstringifiable value]"
        }
    }
}

function Re(e, t) {
    var r = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
        var n = Object.getOwnPropertySymbols(e);
        t && (n = n.filter(function(t) {
            return Object.getOwnPropertyDescriptor(e, t).enumerable
        })), r.push.apply(r, n)
    }
    return r
}

function Ie(e) {
    for (var t = 1; t < arguments.length; t++) {
        var r = null != arguments[t] ? arguments[t] : {};
        t % 2 ? Re(Object(r), !0).forEach(function(t) {
            J(e, t, r[t])
        }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(r)) : Re(Object(r)).forEach(function(t) {
            Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(r, t))
        })
    }
    return e
}

function Ne(e, t) {
    const r = {
        kind: "Unknown",
        type: Ue(e),
        name: void 0,
        message: void 0,
        stack: void 0,
        code: void 0,
        details: {},
        inner: void 0
    };
    if (e instanceof ce) return r.kind = "FetchRichError", r.message = "".concat(e.message, "::").concat(je(e.context)), r.code = e.code, null != e && e.cause && (r.details.cause = Ne(null == e ? void 0 : e.cause, t)), Le(r, t);
    if (!e) return r.kind = "ThrownValue", r.message = String(e), Le(r, t);
    if (s = e, "[object PromiseRejectionEvent]" === Object.prototype.toString.call(s) || s instanceof PromiseRejectionEvent) {
        var n, i, o;
        r.kind = "PromiseRejectionEvent";
        const s = "".concat((null == e || null === (n = e.reason) || void 0 === n ? void 0 : n.message) || (null == e || null === (i = e.reason) || void 0 === i ? void 0 : i.type) || (null == e ? void 0 : e.reason)).trim();
        return r.message = s || "Unhandled promise rejection", r.details = qe(e, ["type", "timeStamp", "isTrusted", "cancelable", "bubbles", "composed"]), Ve(() => !!e.promise) && (r.details.hasPromise = !0), r.inner = De(e.reason, t, 1), r.stack = null === (o = r.inner) || void 0 === o ? void 0 : o.stack, Le(r, t)
    }
    var s, a;
    if (a = e, "[object ErrorEvent]" === Object.prototype.toString.call(a) || a instanceof ErrorEvent) {
        var c, l;
        const n = e;
        r.kind = "ErrorEvent", r.message = null !== (c = null == n ? void 0 : n.message) && void 0 !== c ? c : "Uncaught error", r.details = qe(n, ["filename", "lineno", "colno", "timeStamp", "type", "isTrusted"]);
        const i = n.error;
        void 0 !== i && (r.inner = De(i, t, 1)), r.stack = null === (l = r.inner) || void 0 === l ? void 0 : l.stack, "string" == typeof r.message && "script error." === r.message.toLowerCase() && (r.details.hint = 'Possibly a cross-origin script error. Ensure proper CORS headers and add crossorigin="anonymous" on script tags, plus Access-Control-Allow-Origin on the asset.');
        const o = ze((null == n ? void 0 : n.target) || (null == n ? void 0 : n.currentTarget));
        return o && (r.details.target = o), Le(r, t)
    }
    if (function(e) {
            return e instanceof Event
        }(e)) {
        var d;
        const n = e;
        r.kind = "Event", r.message = null !== (d = Ve(() => n.type)) && void 0 !== d ? d : "Event", r.details = qe(n, ["type", "timeStamp", "isTrusted", "cancelable", "bubbles", "composed"]);
        const i = ze((null == n ? void 0 : n.target) || (null == n ? void 0 : n.currentTarget));
        return i && (r.details.target = i), Le(r, t)
    }
    if (function(e) {
            const t = e,
                r = "string" == typeof(null == t ? void 0 : t.name),
                n = "string" == typeof(null == t ? void 0 : t.message),
                i = null == t ? void 0 : t.code;
            return !!("[object DOMException]" === Object.prototype.toString.call(e) || r && ("number" == typeof i || /^(SecurityError|NotAllowedError|AbortError|InvalidStateError)$/.test(t.name)) && n)
        }(e)) {
        const n = e;
        return r.kind = "DOMException", r.name = n.name, r.code = null == n ? void 0 : n.code, r.message = n.message || n.toString() || "DOMException", r.stack = null == n ? void 0 : n.stack, Le(r, t)
    }
    if (e instanceof Error) {
        const n = e;
        r.kind = "Error", r.name = n.name, r.message = n.message || ("function" == typeof n.toString ? n.toString() : "Error"), r.stack = n.stack;
        const i = Ve(() => n.cause);
        void 0 !== i && (r.details.cause = De(i, t, 1));
        const o = Ve(() => n.errors);
        return Array.isArray(o) && (r.details.errors = o.slice(0, 50).map(e => De(e, t, 1)), o.length > 50 && (r.details.errorsTruncated = o.length - 50)), Le(r, t)
    }
    return "object" == typeof e ? (r.kind = "ThrownValue", r.message = We(e), r.details = {
        valueType: typeof e,
        valuePreview: Ge(e, t.maxStringLength),
        object: He(e, 50)
    }, Le(r, t)) : (r.kind = "ThrownValue", r.message = We(e), r.details = {
        valueType: typeof e,
        valuePreview: Ge(e, t.maxStringLength)
    }, Le(r, t))
}

function Le(e, t) {
    return "string" == typeof e.message && (e.message = Ke(e.message, t.maxStringLength)), "string" == typeof e.stack && (e.stack = Ke(e.stack, t.maxStringLength)), e.message || (e.message = e.name || e.type || e.kind || "Unknown error"), !e.name && "string" == typeof e.type && e.type.endsWith("Error") && (e.name = e.type), e
}

function De(e, t, r) {
    if (r > t.maxDepth) return {
        kind: "Truncated",
        type: "Truncated",
        message: "[Max depth reached]",
        details: {}
    };
    const n = Ne(e, Ie({}, t));
    return n.details && (n.details = He(n.details, 30)), n
}

function Ue(e) {
    const t = Ve(() => {
        var t;
        return null == e || null === (t = e.constructor) || void 0 === t ? void 0 : t.name
    });
    if (t) return t;
    const r = Ve(() => Object.prototype.toString.call(e));
    return "string" == typeof r ? r.slice(8, -1) : typeof e
}

function ze(e) {
    if (!e || "object" != typeof e) return null;
    const t = e,
        r = Ve(() => t.tagName),
        n = Ve(() => t.id),
        i = Ve(() => t.className),
        o = Ve(() => t.src),
        s = Ve(() => t.href),
        a = Ve(() => t.currentSrc),
        c = {};
    return r && (c.tagName = String(r)), n && (c.id = String(n)), i && "string" == typeof i && (c.className = i), o && (c.src = String(o)), a && (c.currentSrc = String(a)), s && (c.href = String(s)), Object.keys(c).length ? c : null
}

function qe(e, t) {
    const r = {};
    for (const n of t) {
        const t = Ve(() => e[n]);
        void 0 !== t && (r[n] = t)
    }
    return r
}

function He(e, t) {
    var r;
    if (!e || "object" != typeof e) return e;
    const n = Array.isArray(e) ? [] : {},
        i = null !== (r = Ve(() => Object.keys(e))) && void 0 !== r ? r : [],
        o = i.slice(0, t);
    for (const s of o) n[s] = Ve(() => e[s]);
    return i.length > t && (n.__keysTruncated = i.length - t), n
}

function Ve(e) {
    try {
        return e()
    } catch (t) {
        return
    }
}

function Ke(e, t) {
    return !t || e.length <= t ? e : "".concat(e.slice(0, Math.max(0, t - 20)), "… [truncated ").concat(e.length - t, " chars]")
}

function We(e) {
    try {
        return "string" == typeof e ? e : "number" == typeof e || "boolean" == typeof e || "bigint" == typeof e ? String(e) : "symbol" == typeof e ? e.toString() : "function" == typeof e ? "[Function ".concat(e.name || "anonymous", "]") : e && "object" == typeof e ? Object.prototype.toString.call(e) || "[object Object]" : String(e)
    } catch (t) {
        return "[Unstringifiable value]"
    }
}

function Ge(e, t) {
    return Ke("string" == typeof e ? e : e && "object" == typeof e ? Ze(e, {
        pretty: !1,
        maxStringLength: t
    }) : We(e), t)
}

function Ze(e, t) {
    const r = !!t.pretty,
        n = "number" == typeof t.maxStringLength ? t.maxStringLength : 2e4,
        i = "undefined" != typeof WeakSet ? new WeakSet : null,
        o = (e, t) => {
            if ("string" == typeof t) return Ke(t, n);
            if ("undefined" != typeof window && t === window) return "[Window]";
            if ("undefined" != typeof document && t === document) return "[Document]";
            if (t && "object" == typeof t) {
                if (i) {
                    if (i.has(t)) return "[Circular]";
                    i.add(t)
                }
                if (t instanceof Error) {
                    const e = {
                            name: t.name,
                            message: t.message,
                            stack: t.stack
                        },
                        r = Ve(() => t.errors);
                    return Array.isArray(r) && (e.errors = r), e
                }
            }
            return t
        };
    try {
        return JSON.stringify(e, o, r ? 2 : 0)
    } catch (s) {
        try {
            return String(e)
        } catch (a) {
            return "[Unstringifiable value]"
        }
    }
}
const Ye = "3.1.0";

function $e(e, t) {
    if (t) try {
        const {
            redirected: r,
            status: n,
            statusText: i,
            type: o,
            headers: s,
            url: a
        } = t;
        e.redirected = r, e.status = n, e.statusText = i, e.type = o, e.url = a, e.resHeaders = function(e) {
            const t = {};
            if (!e) return t;
            try {
                if ("undefined" != typeof Headers && e instanceof Headers && "function" == typeof e.forEach) return e.forEach(function(e, r) {
                    t[String(r)] = String(e)
                }), t
            } catch (r) {}
            if (Array.isArray(e)) {
                for (let r = 0; r < e.length; r++) {
                    let n = e[r];
                    n && n.length >= 2 && (t[String(n[0])] = String(n[1]))
                }
                return t
            }
            if ("object" == typeof e)
                for (let n in e) Object.prototype.hasOwnProperty.call(e, n) && (t[String(n)] = String(e[n]));
            return t
        }(s)
    } catch (r) {
        e.err = "Error during enrich req context: ".concat(String(r))
    }
}
async function Je(e, t, r) {
    const n = t.method,
        i = t.headers,
        o = ((e, t, r = {}) => ({
            retries: [],
            redirected: !1,
            status: 0,
            statusText: "",
            type: "",
            url: e,
            method: t,
            headers: me({}, r)
        }))(e, n, i),
        {
            retryDelay: s,
            retryEnabled: a,
            retries: c
        } = r,
        l = async n => {
            const i = await oe(e, t, r.requestTimeout),
                a = ((e, t, r, n) => {
                    var i, o;
                    const s = null !== (i = null === (o = t.answer) || void 0 === o ? void 0 : o.status) && void 0 !== i ? i : 0,
                        a = 498 === s,
                        c = 0 === r.retries || n >= r.retries;
                    if (a) return !1;
                    const l = Array.isArray(r.retryOn) ? r.retryOn : [],
                        d = !(!l.length || !l.includes(s)),
                        u = s >= 500;
                    return (s >= 400 && s <= 599 || t.error) && e.retries.push("att-".concat(n + 1, "::msg-").concat(String(null == t ? void 0 : t.error), "::status").concat(s)), !c && !!(t.error || d || u)
                })(o, i, r, n);
            return $e(o, i.answer), a ? (await (c = Math.max(1e3, s), new Promise(e => setTimeout(e, c))), l(n + 1)) : pe(i, o);
            var c
        };
    if (a && c > 0) return l(0);
    const d = await oe(e, t, r.requestTimeout);
    return $e(o, d.answer), pe(d, o)
}
const Qe = ["baseUrlIncluded"],
    Xe = ["baseUrlIncluded"];

function et(e, t) {
    var r = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
        var n = Object.getOwnPropertySymbols(e);
        t && (n = n.filter(function(t) {
            return Object.getOwnPropertyDescriptor(e, t).enumerable
        })), r.push.apply(r, n)
    }
    return r
}

function tt(e) {
    for (var t = 1; t < arguments.length; t++) {
        var r = null != arguments[t] ? arguments[t] : {};
        t % 2 ? et(Object(r), !0).forEach(function(t) {
            J(e, t, r[t])
        }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(r)) : et(Object(r)).forEach(function(t) {
            Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(r, t))
        })
    }
    return e
}
class rt {
    constructor(e) {
        const {
            baseUrl: t,
            requestTimeout: r = X,
            retryAttempts: n = te,
            retryDelay: i = ee,
            retryOn: o = [],
            retryEnabled: s = !0,
            headers: a
        } = e;
        this.baseUrl = t, this.headers = a, this.retryBaseConfig = {
            retries: n,
            retryDelay: i,
            retryOn: o,
            requestTimeout: r,
            retryEnabled: s
        }
    }
    async get(e, t = {}, r) {
        const {
            baseUrlIncluded: n
        } = t, i = Q(t, Qe), o = n ? e : "".concat(this.baseUrl).concat(e), s = tt(tt({}, this.retryBaseConfig), r), a = tt(tt({}, i), {}, {
            method: "GET",
            headers: tt(tt({}, this.headers), (null == i ? void 0 : i.headers) && tt({}, null == i ? void 0 : i.headers))
        });
        return await Je(o, a, s)
    }
    async post(e, t = {}, r) {
        const {
            baseUrlIncluded: n
        } = t, i = Q(t, Xe), o = n ? e : "".concat(this.baseUrl).concat(e), s = tt(tt({}, this.retryBaseConfig), r), a = tt(tt({}, i), {}, {
            method: "POST",
            headers: tt(tt(tt({}, this.headers), (null == i ? void 0 : i.headers) && tt({}, null == i ? void 0 : i.headers)), {}, {
                "Content-Type": "application/json"
            })
        });
        return await Je(o, a, s)
    }
}
var nt = (e => (e.CT = "CT", e.OTT = "OTT", e))(nt || {}),
    it = (e => (e.INFO = "INFO", e.ERROR = "ERROR", e))(it || {});
const ot = ["challenge"];

function st(e, t) {
    var r = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
        var n = Object.getOwnPropertySymbols(e);
        t && (n = n.filter(function(t) {
            return Object.getOwnPropertyDescriptor(e, t).enumerable
        })), r.push.apply(r, n)
    }
    return r
}

function at(e) {
    for (var t = 1; t < arguments.length; t++) {
        var r = null != arguments[t] ? arguments[t] : {};
        t % 2 ? st(Object(r), !0).forEach(function(t) {
            J(e, t, r[t])
        }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(r)) : st(Object(r)).forEach(function(t) {
            Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(r, t))
        })
    }
    return e
}
class ct {
    constructor(e) {
        const {
            httpService: t,
            reportsBaseUrl: r
        } = e;
        this.httpService = t, this.reportsBaseUrl = r
    }
    async report(e, t, r = {
        challenge: null
    }) {
        var n, i, o, s, a, c, l, d, u, h, p, g, m;
        const {
            challenge: b
        } = r, f = Q(r, ot), {
            ua: y,
            browser: v,
            browser_v: w,
            os: S,
            os_v: k,
            engine: O,
            platform: M
        } = Ce, x = function(e, t = {}) {
            let r = "";
            try {
                const n = Ie({
                    maxDepth: 6,
                    maxStringLength: 2e4,
                    pretty: !1
                }, t);
                r = Ze(Ne(e, n), {
                    pretty: !!n.pretty,
                    maxStringLength: n.maxStringLength
                })
            } catch (n) {
                r = "Stringify error problem. Original input ".concat(String(e))
            }
            return r
        }(e), T = Date.now(), E = "".concat(t, "::").concat(x, "::ts-").concat(T), F = null != e && e.meta ? JSON.stringify(null == e ? void 0 : e.meta) : "", P = "w".concat(null === (n = window) || void 0 === n ? void 0 : n.innerWidth, "::h").concat(null === (i = window) || void 0 === i ? void 0 : i.innerHeight), B = "w".concat(null === (o = window) || void 0 === o || null === (o = o.screen) || void 0 === o ? void 0 : o.width, "::h").concat(null === (s = window) || void 0 === s || null === (s = s.screen) || void 0 === s ? void 0 : s.height), C = (null === (a = window) || void 0 === a || null === (a = a.location) || void 0 === a ? void 0 : a.origin) || "", A = (null === (c = document) || void 0 === c ? void 0 : c.referrer) || "", _ = (null === (l = navigator) || void 0 === l ? void 0 : l.language) || "", j = Intl && (null === Intl || void 0 === Intl || null === (d = Intl.DateTimeFormat()) || void 0 === d || null === (d = d.resolvedOptions()) || void 0 === d ? void 0 : d.timeZone) || "", R = null === (u = navigator) || void 0 === u ? void 0 : u.onLine, I = null !== (h = navigator) && void 0 !== h && h.connection ? je({
            dlink: null === (p = navigator) || void 0 === p || null === (p = p.connection) || void 0 === p ? void 0 : p.downlink,
            etype: null === (g = navigator) || void 0 === g || null === (g = g.connection) || void 0 === g ? void 0 : g.effectiveType,
            rtt: null === (m = navigator) || void 0 === m || null === (m = m.connection) || void 0 === m ? void 0 : m.rtt
        }) : "", N = "0" === Ye[0] ? "1" : Ye, L = window[re] ? performance.now() - window[re] : "", D = {
            type: it.ERROR,
            message: E,
            url: window.location.href,
            ua: y,
            browser: v,
            browser_v: w,
            os: S,
            os_v: k,
            engine: O,
            platform: M,
            challenge: b,
            extra: at(at(at(at(at(at(at(at(at(at({
                viewport: P,
                screen: B
            }, "object" == typeof f && f), void 0 !== R && {
                online: String(R)
            }), C && {
                origin: String(C)
            }), A && {
                ref: String(A)
            }), _ && {
                lang: String(_)
            }), j && {
                timeZone: String(j)
            }), I && {
                connect: String(I)
            }), {
                ver: N
            }), L && {
                sdkLifeTime: String(L)
            }), F && {
                challengeMetrics: F
            })
        }, U = JSON.stringify(D), z = "".concat(this.reportsBaseUrl ? this.reportsBaseUrl : "", "/api/v1/report"), q = at({
            body: U
        }, this.reportsBaseUrl && {
            baseUrlIncluded: !0
        });
        this.httpService.post(z, q, {
            retries: 0
        })
    }
}

function lt(e, t) {
    var r = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
        var n = Object.getOwnPropertySymbols(e);
        t && (n = n.filter(function(t) {
            return Object.getOwnPropertyDescriptor(e, t).enumerable
        })), r.push.apply(r, n)
    }
    return r
}

function dt(e) {
    for (var t = 1; t < arguments.length; t++) {
        var r = null != arguments[t] ? arguments[t] : {};
        t % 2 ? lt(Object(r), !0).forEach(function(t) {
            J(e, t, r[t])
        }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(r)) : lt(Object(r)).forEach(function(t) {
            Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(r, t))
        })
    }
    return e
}
const ut = "X-Wbaas-Token";
class ht {
    constructor(e) {
        J(this, "httpService", null), J(this, "features", null), J(this, "cookieName", null), J(this, "trackerPath", null), J(this, "trackerOpts", null), J(this, "reportsBaseUrl", null), J(this, "tracker", null), J(this, "reportTimerId", void 0), J(this, "reportPeriodMs", 1e4);
        const {
            httpService: t,
            settings: r,
            cookieName: n,
            reportsBaseUrl: i
        } = e, {
            path: o,
            feat: s,
            throttleMs: a,
            maxPoints: c,
            autoStart: l,
            reportMs: d
        } = r;
        if (!o) throw new Error("Required constructor options are missing. Please check the documentation.");
        if (window[ht.instanceKey]) return window[ht.instanceKey];
        window[ht.instanceKey] = this, this.httpService = t, this.reportsBaseUrl = i, this.features = null != s ? s : [], this.cookieName = n, this.trackerOpts = {
            throttleMs: a,
            maxPoints: c,
            autoStart: l
        }, this.trackerPath = o, this.reportPeriodMs = null != d ? d : this.reportPeriodMs, this.report = this.report.bind(this)
    }
    async collect() {
        !Array.isArray(this.features) || 0 === this.features.length || (this.tracker = await this.ensureTracker(), this.startReporting())
    }
    async stop() {
        this.tracker && (this.tracker.stop(), this.report(), clearInterval(this.reportTimerId), this.reportTimerId = void 0)
    }
    async startReporting() {
        var e;
        await this.stop(), null === (e = this.tracker) || void 0 === e || e.start(), this.reportTimerId = setInterval(this.report, this.reportPeriodMs)
    }
    async ensureTracker() {
        if (this.tracker) return this.tracker;
        const e = await _e(this.trackerPath);
        return this.tracker = new e(this.features, this.trackerOpts), this.tracker
    }
    async report() {
        var e;
        const t = function(e) {
            const t = "; ".concat(document.cookie).split("; ".concat(e, "="));
            if (2 === t.length) return t.pop().split(";").shift()
        }(this.cookieName);
        if (t && null !== (e = this.tracker) && void 0 !== e && e.hasData) {
            var r;
            const e = dt(dt({}, this.tracker.getRaw()), {}, {
                    time: Date.now()
                }),
                n = this.encodeData(e, t),
                i = "".concat(this.reportsBaseUrl ? this.reportsBaseUrl : "", "/api/v1/frontend-analytics"),
                o = dt({
                    body: n,
                    headers: {
                        [ut]: t
                    }
                }, this.reportsBaseUrl && {
                    baseUrlIncluded: !0
                });
            null === (r = this.httpService) || void 0 === r || r.post(i, o).catch(() => {}), this.tracker.reset()
        }
    }
    encodeData(e, t) {
        const r = function(e, t) {
            const r = [],
                n = function(e, t) {
                    const r = "string" == typeof e,
                        n = r ? be(e) : e,
                        i = be(t);
                    for (let o = 0; o < n.length; o += 1) n[o] = n[o] ^ i[o % i.length];
                    return r ? n : String.fromCharCode.apply(String, n)
                }(e, t);
            for (let i = 0; i < n.length; i += 1) r.push(n[i].toString(16));
            return r.join(",")
        }(JSON.stringify(e), t);
        return JSON.stringify(function() {
            let e = "",
                t = 0;
            for (; t < 1;) e += "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz".charAt(Math.floor(52 * Math.random())), t += 1;
            return e
        }() + function(e) {
            const t = (new TextEncoder).encode(e);
            let r = "";
            for (let n = 0; n < t.length; n += 1) r += String.fromCharCode(t[n]);
            return btoa(r)
        }(r))
    }
}
var pt, gt;
J(ht, "instanceKey", "ANALY_S_WB_KEY"), (gt = pt || (pt = {})).EN = "en", gt.RU = "ru", gt.AM = "am", gt.AZ = "az", gt.KA = "ka", gt.TG = "tg", gt.HY = "hy", gt.UZ = "uz", gt.KK = "kk", gt.KY = "ky";
var mt = pt.EN;

function bt(e) {
    if (! function(e) {
            if (!e) return !1;
            var t = e.trim();
            return t.length > 0 && !t.includes("{{")
        }(e)) return null;
    var t = e.trim().toLowerCase().replace(/_/g, "-").split("-")[0];
    return t.length > 0 ? t : null
}
var ft = Object.values(pt),
    yt = {
        en: pt.EN,
        ru: pt.RU,
        am: pt.AM,
        az: pt.AZ,
        ka: pt.KA,
        tg: pt.TG,
        hy: pt.HY,
        uz: pt.UZ,
        kk: pt.KK,
        ky: pt.KY
    };

function vt(e) {
    return ft.includes(e)
}

function wt(e, t) {
    var r = Object.keys(e);
    if (Object.getOwnPropertySymbols) {
        var n = Object.getOwnPropertySymbols(e);
        t && (n = n.filter(function(t) {
            return Object.getOwnPropertyDescriptor(e, t).enumerable
        })), r.push.apply(r, n)
    }
    return r
}

function St(e) {
    for (var t = 1; t < arguments.length; t++) {
        var r = null != arguments[t] ? arguments[t] : {};
        t % 2 ? wt(Object(r), !0).forEach(function(t) {
            J(e, t, r[t])
        }) : Object.getOwnPropertyDescriptors ? Object.defineProperties(e, Object.getOwnPropertyDescriptors(r)) : wt(Object(r)).forEach(function(t) {
            Object.defineProperty(e, t, Object.getOwnPropertyDescriptor(r, t))
        })
    }
    return e
}
class kt {
    constructor(e) {
        J(this, "lang", function() {
            var e, t = bt(void 0);
            if (t && vt(t)) return yt[t];
            var r = bt(null === (e = null === document || void 0 === document ? void 0 : document.documentElement) || void 0 === e ? void 0 : e.lang);
            return r && vt(r) ? yt[r] : function(e) {
                var t, r;
                void 0 === e && (e = mt);
                var n = "object" == typeof window ? window.navigator : void 0;
                if (!n) return e;
                var i = Array.isArray(n.languages) && n.languages.length > 0 ? n.languages : [n.language];
                try {
                    for (var o = function(e) {
                            var t = "function" == typeof Symbol && Symbol.iterator,
                                r = t && e[t],
                                n = 0;
                            if (r) return r.call(e);
                            if (e && "number" == typeof e.length) return {
                                next: function() {
                                    return e && n >= e.length && (e = void 0), {
                                        value: e && e[n++],
                                        done: !e
                                    }
                                }
                            };
                            throw new TypeError(t ? "Object is not iterable." : "Symbol.iterator is not defined.")
                        }(i), s = o.next(); !s.done; s = o.next()) {
                        var a = bt(s.value);
                        if (a && vt(a)) return yt[a]
                    }
                } catch (c) {
                    t = {
                        error: c
                    }
                } finally {
                    try {
                        s && !s.done && (r = o.return) && r.call(o)
                    } finally {
                        if (t) throw t.error
                    }
                }
                return e
            }()
        }()), J(this, "baseUrl", null), J(this, "reportsBaseUrl", null), J(this, "siteKey", null), J(this, "sdkVersion", null), J(this, "cookieName", "x_wbaas_token"), J(this, "settings", null), J(this, "httpService", null), J(this, "loggerService", null), J(this, "analyticsService", null), J(this, "challengeSolver", null);
        const {
            baseUrl: t,
            siteKey: r
        } = e;
        if (!t || !r) throw new Error("Required constructor options are missing. Please check the documentation.");
        if (kt.instanceKey = (n = e, "".concat("ANTI_SDK_WB", "_").concat(fe(JSON.stringify(n)))), window[kt.instanceKey]) return window[kt.instanceKey];
        var n, i;
        window[re] = null === (i = window) || void 0 === i || null === (i = i.performance) || void 0 === i ? void 0 : i.now(), window[kt.instanceKey] = this, this.init(e)
    }
    async init(e) {
        const {
            baseUrl: t,
            siteKey: r,
            requestTimeout: n,
            retryAttempts: i,
            retryDelay: o,
            retryEnabled: s,
            retryOn: a,
            cookieName: c,
            reportsBaseUrl: l,
            lang: d
        } = e;
        try {
            this.createToken = this.createToken.bind(this), this.createOneTimeToken = this.createOneTimeToken.bind(this), this.lang = null != d ? d : this.lang, this.baseUrl = t, this.reportsBaseUrl = null != l ? l : null, this.siteKey = r, this.cookieName = null != c ? c : this.cookieName, this.sdkVersion = "js-front-".concat(Be.getPlatform().type, "/").concat("3.1.0");
            const e = {
                headers: {
                    "X-Guardium-Antibot-Key": this.siteKey,
                    "X-Guardium-Antibot-SDK-Version": this.sdkVersion
                },
                baseUrl: t,
                requestTimeout: n,
                retryAttempts: i,
                retryDelay: o,
                retryEnabled: s,
                retryOn: a
            };
            this.loadSettings = function(e) {
                let t = null;
                return (...r) => t || (t = e(...r).then(e => (t = null, e), e => {
                    throw t = null, e
                }), t)
            }(this.loadSettings.bind(this)), this.httpService = new rt(e), this.loggerService = new ct({
                httpService: this.httpService,
                reportsBaseUrl: l
            }), this.analyticsService = await this.initAnalyticsService(), this.analyticsService.collect()
        } catch (h) {
            var u;
            throw null === (u = this.loggerService) || void 0 === u || u.report(h, "init").catch(() => {}), h
        }
    }
    async createToken(e) {
        try {
            return await this.createTokenWithRetries(null != e ? e : {}, nt.CT, "/api/v1/create-token")
        } catch (n) {
            var t, r;
            const i = {
                challenge: null !== (t = null == e ? void 0 : e.challenge) && void 0 !== t ? t : {}
            };
            throw null == this || null === (r = this.loggerService) || void 0 === r || r.report(n, nt.CT, i).catch(() => {}), n
        }
    }
    async createOneTimeToken(e) {
        try {
            return await this.createTokenWithRetries(e, nt.OTT, "/api/v1/create-one-time-token")
        } catch (n) {
            var t, r;
            const i = {
                challenge: null !== (t = null == e ? void 0 : e.challenge) && void 0 !== t ? t : {}
            };
            throw null == this || null === (r = this.loggerService) || void 0 === r || r.report(n, nt.OTT, i).catch(() => {}), n
        }
    }
    async createTokenWithRetries(e, t, r) {
        this.challengeSolver || (this.challengeSolver = await this.initChallengeSolver());
        try {
            var n;
            const t = JSON.stringify(null != e ? e : {}),
                {
                    secureToken: i
                } = await (null == this || null === (n = this.httpService) || void 0 === n ? void 0 : n.post(r, {
                    body: t
                }));
            return this.challengeSolver.finish().then(() => i)
        } catch (i) {
            if (i instanceof ae) {
                const n = await this.challengeSolver.solve(i.challenge),
                    o = this.enrichPayload(e, n);
                return this.createTokenWithRetries(o, t, r)
            }
            throw await this.challengeSolver.close(), i
        }
    }
    enrichPayload(e, t) {
        const {
            secureToken: r
        } = e;
        return St(St(St({}, r && {
            secureToken: r
        }), this.isOTTPayload(e) && {
            action: e.action,
            userScope: e.userScope
        }), t)
    }
    isOTTPayload(e) {
        return "object" == typeof e && null !== e && "action" in e
    }
    async initChallengeSolver() {
        if (this.challengeSolver) return this.challengeSolver;
        const e = await this.loadSettings(),
            {
                solverConfig: t,
                solverPath: r
            } = e,
            n = await _e("".concat(this.baseUrl).concat(r)),
            i = St({
                lang: this.lang,
                metricsEnabled: !1
            }, t && t);
        return new n(this.baseUrl, i)
    }
    async initAnalyticsService() {
        var e, t;
        if (this.analyticsService) return this.analyticsService;
        this.settings = await this.loadSettings();
        const r = {
            httpService: this.httpService,
            cookieName: this.cookieName,
            reportsBaseUrl: this.reportsBaseUrl,
            settings: St(St({}, null === (e = this.settings) || void 0 === e ? void 0 : e.analytics), {}, {
                path: "".concat(this.baseUrl).concat(null === (t = this.settings) || void 0 === t || null === (t = t.analytics) || void 0 === t ? void 0 : t.path)
            })
        };
        return this.analyticsService = new ht(r), this.analyticsService
    }
    async loadSettings() {
        var e;
        return this.settings || (this.settings = await (null === (e = this.httpService) || void 0 === e ? void 0 : e.post("/api/v1/find-frontend-settings", {}, {
            retries: 0
        }))), this.settings
    }
}
const Ot = "x_wbaas_token";
window.addEventListener("DOMContentLoaded", async () => {
    if (!window.IS_OUTDATED_BROWSER) try {
        const t = e();
        if (function(e) {
                const t = document.getElementById("c_cont"),
                    r = document.getElementById("wait_msg");
                if (!t || !r) throw new Error("Required DOM elements not found");
                if (e) G(r, function() {
                    const e = document.createElement("div");
                    e.className = "w_i wrapper__item__default";
                    const t = document.createElement("p");
                    return t.classList.add("wait_msg"), t.textContent = H(M), e.appendChild(t), e
                }(), function() {
                    const e = document.createElement("div");
                    return e.classList.add("loader"), e
                }()), t.appendChild(r);
                else {
                    const e = function() {
                        const e = document.createElement("div");
                        e.className = "w_i warn_msg";
                        const t = document.createElement("p");
                        return t.innerHTML = H(x), e.appendChild(t), e
                    }();
                    t.appendChild(e)
                }
            }(t), !t) return;
        if (!i.isCreateTokenAllowed()) throw new Error("Get token tries exceeded");
        await async function(e) {
            const t = document.querySelector("#s-key"),
                r = String(t.dataset.siteKey),
                n = new kt({
                    baseUrl: "/__wbaas/challenges/antibot",
                    siteKey: r,
                    lang: q
                });
            e.registerAttempt();
            const i = function(e) {
                    const t = `; ${document.cookie}`.split(`; ${e}=`);
                    if (2 === t.length) return t.pop().split(";").shift()
                }(Ot),
                o = await (i ? n.createToken({
                    secureToken: i
                }) : n.createToken());
            if (!o) throw new Error("Token did not received. Try again.");
            ! function(e, t, r = {}) {
                (r = {
                    path: "/",
                    ...r
                }).expires instanceof Date && (r.expires = r.expires.toUTCString());
                let n = `${e}=${t}`;
                for (let i in r) {
                    n += "; " + i;
                    let e = r[i];
                    !0 !== e && (n += "=" + e)
                }
                document.cookie = n
            }(Ot, o, {
                secure: !0,
                SameSite: "None",
                "max-age": "1209600"
            }), document.location.reload()
        }(i)
    } catch (t) {
        const e = o(t);
        Z(function(e) {
                const t = (new TextEncoder).encode(e);
                let r = "";
                for (let n = 0; n < t.length; n += 1) r += String.fromCharCode(t[n]);
                return btoa(r)
            }(JSON.stringify(e))),
            function(e) {
                let t;
                t = e instanceof Error ? o(e) : e;
                const r = JSON.stringify(t);
                fetch("/__wbaas/challenges/antibot/api/v1/report", {
                    body: r,
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json;charset=UTF-8"
                    }
                })
            }(e)
    }
});