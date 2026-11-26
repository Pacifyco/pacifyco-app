# Manual test script (staging)

Phase 14's manual pass: click through Pacifyco on staging as a parent, a sitter and an admin, and check each
step does what it says. It takes about 2 hours, and it's fine to do it over a few sittings.

**When something's wrong:** note the section and step number (for example "6.3"), what you did, what you
expected and what happened. Add a screenshot if it helps. Put it in `docs/beta-feedback.md` under "Manual
pass", or just tell me in chat.

---

## 0. Before you start

### 0.1 Your three test accounts

You need three accounts with **different emails** (one email = one account = one role):

| Account | What it needs before the seed |
| --- | --- |
| **Admin** | Your existing staging admin. |
| **Test parent** | Signed up as a parent with the profile finished, and **at least one child verified** (approved by the admin). |
| **Test sitter** | Signed up as a sitter, application approved by the admin, **level set to Pause**, payment details filled in, and her weekly hours set (Availability). |

Section 1 below walks you through making a parent and a sitter from scratch. If you don't have the test parent
and test sitter yet, do sections 1 and 2 first, then run the seed (0.2), then carry on from section 3.

### 0.2 Fill staging with fake people (the seed)

The seed adds 12 sitters (4 at each level), 8 families and about 27 bookings between them, plus 7 bookings
for your own test parent and test sitter. Seeded people are display only: no one can sign in as them and
they're never emailed. Their cards show initials, not photos.

In your own terminal (PowerShell), from the repo:

```powershell
cd api
$env:ENVIRONMENT = "staging"
$env:MIGRATION_DATABASE_URL = "<staging's MIGRATION_DATABASE_URL, from your password manager>"
.venv\Scripts\python -m app.cli seed-staging --parent-email <test parent email> --sitter-email <test sitter email>
```

That only says what it would do. If it looks right, run the same line again with `--yes` on the end.

- To start again later: run it with `--replace --yes`.
- To take it all out: run it with `--remove --yes`. Your own accounts stay.
- Never type the database URL into chat. It holds the database password.

**What the seed gives your test accounts:**

| # | Who | Booking | Used in |
| --- | --- | --- | --- |
| A | Test parent + test sitter | **Today**, starting this hour, 2 hours, paid | 6 (check-in, overtime, check-out) |
| B | Test parent + Ananya Rao | Finished 3 days ago, not reviewed yet | 7.1 (review) |
| C | Test parent + Divya Menon | In 3 days, paid | 8.1 (cancel) |
| D | Test parent + Priya Shetty | In 2 days, accepted, waiting for payment | 5.1 (pay) |
| E | Rohan Mehta + test sitter | A request, in 2 days | 4.4 (accept) |
| F | Karthik Subramanian + test sitter | Finished 2 hours ago, her pay due | 7.3 (payout) |
| G | Meera Bhat + test sitter | In 4 days, paid | 10.3 (her booking page) |

Booking A starts the hour you run the seed. Run it on the day you'll do section 6.

### 0.3 Browsers

Use **three browser windows** so you can be all three people at once:
- **Chrome:** the admin.
- **A Chrome Incognito window** (Ctrl+Shift+N): the test parent.
- **Edge, or a second Chrome profile:** the test sitter.

Do the parent and sitter steps on a **phone** at least once (the app is mobile first). Section 12 says how.

---

## 1. Signing up (a brand-new email)

| Step | Do | Expect |
| --- | --- | --- |
| 1.1 | On the staging site, sign in with a new email address. Use the email code. | The code arrives by email and signs you in. |
| 1.2 | First sign-in. | You're asked only to choose **parent** or **sitter**, then to confirm ("You're joining as a parent. Is that right?"). |
| 1.3 | Choose parent and confirm. | You land straight in the parent area, with "finish your profile" steps. |
| 1.4 | Sign out, then sign in again with **Google** (a different Google account). | It signs in and asks for the role the same way. |
| 1.5 | In "Your details", enter a pin code outside the service area (for example 560010). | It's refused, saying Pacifyco isn't in that area yet. |

## 2. A parent finishing their profile

| Step | Do | Expect |
| --- | --- | --- |
| 2.1 | Open "Your children" before giving consent. | It says "Your consent comes first". |
| 2.2 | Parental consent: read the page, tick the boxes, tick the terms. | Nothing is pre-ticked. You can't continue without the required ones and the terms. The optional "offers and updates" box isn't needed. The links open the Family Terms and the Privacy policy. |
| 2.3 | Your details: name, Indian mobile number, address, pin code 560034, relationship (Mother, Father or Legal guardian). | It saves. Each page shows "Step N of 4" and the bar moves. |
| 2.4 | Add a child with a date of birth **under 18 months**. | It's allowed on the profile, but section 4.2 will refuse booking for this child. |
| 2.5 | Add a child aged 2+ with a birth certificate (a JPG, PNG or PDF under 5 MB). | It saves and shows "being checked". |
| 2.6 | Try uploading a 6 MB file, then a `.docx`. | Both refused, with a clear message. |
| 2.7 | Emergency contact: name, relationship, phone, and the permission tick. | It saves. Then only "Your profile is under review." shows. |
| 2.8 | **Admin:** Verifications. Open the birth certificate, then approve it. | The document opens in a new tab. The child becomes verified, and the parent is emailed. |
| 2.9 | **Admin:** reject a certificate (add another child for this) with a reason. | The parent sees the reason and can upload again. |
| 2.10 | **Admin:** Document access log. | Your views from 2.8 are listed. |

## 3. Finding a sitter (test parent)

| Step | Do | Expect |
| --- | --- | --- |
| 3.1 | Open Sitters. | Seeded sitters appear (12 or so, plus your test sitter), nearest first. Cards show initials, an hourly rate ("₹499/hour", "from ₹699/hour" or "₹899/hour"), area, ages and experience. |
| 3.2 | Look for the words Pause, Unwind or Recharge anywhere. | **Never shown to parents.** Only rates. |
| 3.3 | Look for sitter pay (₹200, ₹300, ₹400 an hour). | **Never shown to parents.** |
| 3.4 | Filter by a day, a part of the day (Morning, Afternoon, Evening, Night), a language (try Tamil) and first aid. Try each sort. | The list changes to match each filter. |
| 3.5 | Open Lakshmi Krishnan's profile. | Her bio, university and semester, languages, rating with written reviews (parent's first name and the month), her week as a grid, and the nudge to book a short first booking with a parent at home. |
| 3.6 | Look for Ritika Sharma. | She's listed. Her strike was 5 days ago and only blocked her for 24 hours. |

## 4. Booking (test parent, then test sitter)

| Step | Do | Expect |
| --- | --- | --- |
| 4.1 | Book your **test sitter**: a free time at least 6 hours from now, 2 hours. Answer the cameras question. | The full price shows, then "request sent". Nothing to pay yet. |
| 4.2 | Try booking with the under-18-months child from 2.4. | Refused. |
| 4.3 | Try a time less than 6 hours away, and a time past 6 pm for a Pause sitter. | Both refused, each with a clear message. |
| 4.4 | **Sitter:** Requests. Open booking E (Rohan Mehta) and your request from 4.1. | Each shows children, ages, allergies, routines, cameras, the pin code area and her pay. **No address, no price, no emergency contact.** A countdown to answer. |
| 4.5 | **Sitter:** accept your request from 4.1, and decline booking E. | The parent is emailed for each. |
| 4.6 | **Test parent:** open the 4.1 booking. | It's accepted and waiting for payment, with the payment deadline (3 hours before the start). |

## 5. Paying (test parent, admin)

| Step | Do | Expect |
| --- | --- | --- |
| 5.1 | Open booking D (Priya Shetty) and the 4.1 booking. Press Pay. | The UPI QR code and link (payee "Pacifyco"), the amount, and a box for the 12-digit UPI reference. |
| 5.2 | Enter a reference with 11 digits. | Refused. |
| 5.3 | Enter a 12-digit reference for D, and a different one for 4.1. | Each shows "being checked". |
| 5.4 | **Admin:** Payments. | Both appear, plus Sana Khan's (seeded, sent a few hours before the seed ran). |
| 5.5 | **Admin:** confirm D. Reject 4.1 with a reason. | D becomes confirmed (parent emailed). On 4.1 the parent sees the reason and can send a new reference. |
| 5.6 | **Test parent:** send a new reference for 4.1. **Admin:** confirm it. | 4.1 is confirmed. |
| 5.7 | **Test parent:** Payments (your payment history). | Every payment and its status. |
| 5.8 | **Sitter:** open the confirmed 4.1 booking. | Now the home address and the emergency contact show. |

## 6. The day of the booking: booking A (test parent and test sitter)

| Step | Do | Expect |
| --- | --- | --- |
| 6.1 | **Test parent:** open booking A. | The 4-digit **check-in code** shows. No check-out code yet. |
| 6.2 | **Test parent:** open booking C (in 3 days). | No code yet: it shows only on the day of the booking. |
| 6.3 | **Sitter:** open booking A and enter a **wrong** code once. | "That code's wrong", with the attempts left. (Don't do 5: that locks it, and only an admin can close it. That's step 9.4.) |
| 6.4 | **Sitter:** enter the right code. When the browser asks for your location, allow it. | Checked in; the booking is under way. |
| 6.5 | **Test parent:** booking A again. | Now the **check-out code** shows. |
| 6.6 | **Test parent:** Request overtime, 1 hour. **Sitter:** accept it. | The sitter is told, and the parent sees it accepted. Nothing is charged yet. |
| 6.7 | Open **Messages** on both sides and send a message each way. | It arrives within about 10 seconds. |
| 6.8 | **Sitter:** check out with the check-out code. | Completed. **If it's after A's booked end**, an overtime charge for the extra time rounded up to the full hour, which the parent must pay within 2 hours. If you check out before the end, no refund. |
| 6.9 | **Test parent:** if there's an overtime charge, try to book anyone. | Refused until it's paid. Then pay it like 5.3 and confirm it as admin. |

## 7. After the booking (reviews and pay)

| Step | Do | Expect |
| --- | --- | --- |
| 7.1 | **Test parent:** open booking B (Ananya Rao) and leave 5 stars and a short review. | It saves. Ananya's profile shows it, and her average and count change. |
| 7.2 | **Sitter:** review the parent on booking A. | It saves. **The parent never sees it**; only admins do. |
| 7.3 | **Sitter:** Earnings. | Booking F's pay is "due to you" (paid within 12 hours), and booking A's too after 6.8. |
| 7.4 | **Admin:** Payouts. | Your test sitter and two seeded sitters (Shruthi Gowda with overtime, Farah Siddiqui), each with a countdown to the 12-hour deadline and their UPI or bank details. |
| 7.5 | **Admin:** mark your test sitter paid with a made-up reference (for example `UTR123456789`). | She's emailed. The Earnings page moves it to paid, with the reference. |
| 7.6 | **Admin:** Audit log. | A `bank_details_viewed` row from 7.4, and rows for the steps above. |

## 8. Cancelling

| Step | Do | Expect |
| --- | --- | --- |
| 8.1 | **Test parent:** cancel booking C (more than 3 hours away). | Cancelled. A full refund is recorded for an admin to pay back. |
| 8.2 | **Admin:** Payments, then the refund. Mark it paid with a reference. | The parent sees the refund as paid. |
| 8.3 | **Sitter:** cancel a confirmed booking of hers more than 8 hours away (make one with the test parent first, as in section 4). | Cancelled; no strike. The parent and the admins are emailed. |
| 8.4 | **Sitter:** Strikes. | No strikes. To test the strike ladder, an admin can add one with a reason on her admin page and then remove it. |

## 9. Emergencies, issues and reports (use a booking under way: make one like section 4 for today if A is done)

| Step | Do | Expect |
| --- | --- | --- |
| 9.1 | **Test parent:** Emergency, choose **emergency (safety or medical)**, add a note. (Not theft or abuse: those suspend the sitter.) | Every admin address is emailed at once. |
| 9.2 | **Admin:** any page. | A red banner. Incidents: acknowledge it, then resolve it with a note. Her pay for that booking is held until it's resolved. |
| 9.3 | **Sitter:** Issues, "running late", with a note. | Admins are emailed; it shows on Complaints as a booking complaint. |
| 9.4 | **Admin:** Overdue check-outs. | Nikita Fernandes's seeded booking under way shows once it's 30 minutes past its end. Close it by hand with a reason. |
| 9.5 | **Sitter:** on a booking that has started: "No one's home" (tick that no child is alone). | The parent and admins are emailed, and a 20-minute countdown shows. **Test parent:** press "I have arrived". |

## 10. The sitter's own pages

| Step | Do | Expect |
| --- | --- | --- |
| 10.1 | Availability: tick a day, press "+" a few times, change a time. | Ticking adds 9 am–1 pm; each "+" adds the next slot (1–4, 4–7, 7–10, 10–12), then nothing more. |
| 10.2 | Check that the parent's view of her week (3.5) matches. | It matches. |
| 10.3 | Bookings: open booking G (Meera Bhat). | Children, routines, cameras, address and the emergency contact (it's paid). Her pay, never the price. |
| 10.4 | **Test parent:** review the test sitter on booking A. **Sitter:** Reviews. | The parent's review shows, with their first name and the month. |

## 11. Help and complaints

| Step | Do | Expect |
| --- | --- | --- |
| 11.1 | **Test parent:** Help, "Raise a complaint", about a booking, with a file attached. | It's sent; admins are emailed. |
| 11.2 | **Admin:** Complaints. | Yours and Sana Khan's (seeded, about her payment), each with time left to the first reply (24 hours) and to resolve (48 hours). |
| 11.3 | **Admin:** reply to yours, then resolve it with a note. | The parent is emailed each time and can read the thread on Help. |
| 11.4 | **Test parent:** disagree and escalate it. | It goes to the Grievance Officer (any admin for now): acknowledge it, then write a decision, which closes it. |
| 11.5 | **Test parent:** Help, "Your data", a data request (access). | It shows on Complaints as a data request. |

## 12. On a phone

Sign in as the test parent (and once as the sitter) on your phone's browser and repeat 3.1, 3.5, 5.1 and 6.1.

| Step | Expect |
| --- | --- |
| 12.1 | Nothing runs off the side of the screen; no sideways scrolling. |
| 12.2 | Buttons are easy to tap; the QR code fits; the codes are big enough to read out. |
| 12.3 | Sitter: check-in on the phone asks for location and works. |

## 13. Admin: accounts

| Step | Do | Expect |
| --- | --- | --- |
| 13.1 | People: find Priya Shetty (seeded), suspend her with a reason (kind "other"). This also cancels booking D, so do it last. | Her upcoming bookings are cancelled and refunded, with no strike; the test parent is told about D (without the reason). She disappears from the Sitters list. |
| 13.2 | Reinstate her with a reason. | She's back in the list. |
| 13.3 | **Test parent:** Your profile, "Close your account" (on the account from section 1, not your main test parent). | Refused while anything is booked ahead or owed. Otherwise it closes, and sign-in shows the account is closed. |
| 13.4 | **Admin:** reopen the closed account. | It works again. |

---

## When you're done

- [ ] Every problem is noted in `docs/beta-feedback.md` (or sent to me), with its step number.
- [ ] If you want staging clean for the user testing, run the seed with `--replace --yes` (fresh bookings for
  today) or `--remove --yes`.
