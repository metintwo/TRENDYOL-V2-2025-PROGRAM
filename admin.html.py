<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="UTF-8">
  <title>Admin Paneli | Kullanıcı Yönetimi</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>
    body { background:#f5f7fb; padding:20px; }
    .card { border-radius:12px; box-shadow:0 4px 10px rgba(0,0,0,0.05); margin-bottom:20px; }
    table { background:#fff; }
  </style>
</head>
<body class="container py-4">

  <!-- ===== ÜST BAR ===== -->
  <div class="d-flex justify-content-between align-items-center mb-4">
    <h2 class="mb-0">⚙️ Admin Paneli</h2>
    <div>
      <span class="me-2">👤 {{ current_user.username }} (Rol: {{ current_user.role }})</span>
      <a href="{{ url_for('dashboard') }}" class="btn btn-dark">📦 Siparişler</a>
      <a href="{{ url_for('questions') }}" class="btn btn-secondary">❓ Sorular</a>
      <a href="{{ url_for('index') }}" class="btn btn-outline-dark">🏠 Ana Sayfa</a>
      <a href="{{ url_for('logout') }}" class="btn btn-danger">🚪 Çıkış</a>
    </div>
  </div>

  <!-- Flash mesajlar -->
  {% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
      {% for category, message in messages %}
        <div class="alert alert-{{ category }}">{{ message }}</div>
      {% endfor %}
    {% endif %}
  {% endwith %}

  <!-- ===== Kullanıcı Yönetimi Tablosu ===== -->
  <div class="card p-3">
    <h4>Kullanıcılar</h4>
    <div class="table-responsive">
      <table class="table table-striped align-middle">
        <thead class="table-dark">
          <tr>
            <th>ID</th>
            <th>Kullanıcı Adı</th>
            <th>Mevcut Rol</th>
            <th>Yeni Rol Ata</th>
          </tr>
        </thead>
        <tbody>
          {% for u in users %}
          <tr>
            <td>{{ u.id }}</td>
            <td>{{ u.username }}</td>
            <td><span class="badge bg-info text-dark">{{ u.role }}</span></td>
            <td>
              <form method="post" action="{{ url_for('change_role', user_id=u.id) }}" class="d-flex gap-2">
                <select name="role" class="form-select">
                  <option value="üye"   {% if u.role=="üye" %}selected{% endif %}>Üye</option>
                  <option value="kargo" {% if u.role=="kargo" %}selected{% endif %}>Kargo</option>
                  <option value="soru"  {% if u.role=="soru" %}selected{% endif %}>Soru</option>
                  <option value="ofis"  {% if u.role=="ofis" %}selected{% endif %}>Ofis</option>
                  <option value="admin" {% if u.role=="admin" %}selected{% endif %}>Admin</option>
                </select>
                <button class="btn btn-primary btn-sm">Kaydet</button>
              </form>
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- ===== JS ===== -->
  <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
