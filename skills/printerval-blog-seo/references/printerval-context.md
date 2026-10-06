# Bối cảnh Printerval và giả định

Tài liệu này ghi những gì đã biết, những gì **chỉ là giả định**, và câu hỏi còn mở. Cập nhật khi có thông tin thật.

## Đã biết (từ yêu cầu của người dùng)

- Mục tiêu: bộ skill SEO cho **blog** của Printerval; tập trung nội dung hữu ích. Không làm audit kỹ thuật.
- Thị trường: **US/UK**, bài tiếng Anh.
- SEO Specialist gửi **file CSV export từ nhóm từ khóa rất rộng**; skill phải đọc và gom nhóm theo yêu cầu.
- URL và sitemap của Printerval đang được tối ưu lại, có nhiều link redirect: **không dựa vào URL/sitemap** hiện tại.
- Link tới sản phẩm do team content thực hiện; blog dẫn sang trang bán hàng một cách tự nhiên.

## Thông tin công khai (từ kết quả tìm kiếm, chưa kiểm chứng trực tiếp vì môi trường chặn truy cập printerval.com)

- Marketplace print-on-demand với seller độc lập: áo, hoodie, poster, canvas, đồ gia dụng, quà cá nhân hóa; bản đa ngôn ngữ (`/es/`, `/uk/`) và help center riêng.
- Con số tự công bố không nhất quán giữa các nguồn (số creator, số khách). Không trích các con số này trong bài nếu chưa có nguồn chính thức từ công ty.
- Nguồn bên thứ ba (Semrush qua snippet tìm kiếm) nêu các đối thủ gần: ArtistShot, TeePublic, Spreadshirt. Thời điểm dữ liệu không rõ.

## Giả định đang dùng (cần xác nhận)

| Giả định | Ảnh hưởng nếu sai |
|---|---|
| Blog phục vụ chủ yếu **người mua** (quà, cá nhân hóa); chưa có nhóm bài cho seller/creator | Cần topic map riêng cho seller (how to sell POD, thiết kế) |
| Taxonomy mặc định (dịp lễ, người nhận, sở thích, sản phẩm, kiến thức) phản ánh catalog | Mở rộng bằng `--extend-taxonomy` hoặc sửa `assets/taxonomy.json` |
| Danh mục sản phẩm đủ rộng để bài gift guide nhắc sản phẩm tự nhiên | Một số cụm có thể không có sản phẩm tương ứng: team content báo lại |
| Ngày xuất bản bài theo mùa cần lead time 12 tuần (bài mới) / 6 tuần (cập nhật) | Hiệu chỉnh bằng seasonality trong GSC/Trends |
| Mặc định thị trường `us` khi file không nêu thị trường | Gán `file.csv::uk` cho file UK |

## Câu hỏi còn mở

1. Blog nằm ở đâu (subfolder, subdomain, CMS riêng)? Có bao nhiêu bài đã đăng, có danh sách slug để `link_plan.py --published` biết bài nào đã live không?
2. Có cấu trúc `/uk/` riêng cho bản Anh không? Bài UK có URL riêng hay dùng chung?
3. Tác giả/biên tập là ai (byline, bio) và có quy trình duyệt sự thật không?
4. Ai sở hữu danh sách IP/nhãn hiệu cần tránh và dữ liệu vận hành (hạn đặt hàng, thời gian giao)?
5. Nguồn dữ liệu keyword đang dùng (Semrush, Ahrefs, Keyword Planner, GSC)? Có thể xuất kèm `serp_urls` để gom theo SERP không?
