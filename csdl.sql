--=====================================================================
-- CSDL SauRieng - Hệ thống chẩn đoán bệnh trên cây sầu riêng
-- SQL Server - Bản thử nghiệm NVARCHAR
--=====================================================================

USE master;
GO

IF DB_ID(N'SauRieng') IS NULL
    CREATE DATABASE SauRieng COLLATE Vietnamese_CI_AS;
GO

USE SauRieng;
GO

-- Xóa bảng cũ nếu cần chạy lại từ đầu
IF OBJECT_ID(N'dbo.DuLieuHuanLuyen', N'U') IS NOT NULL DROP TABLE dbo.DuLieuHuanLuyen;
IF OBJECT_ID(N'dbo.KetQuaChanDoan',  N'U') IS NOT NULL DROP TABLE dbo.KetQuaChanDoan;
IF OBJECT_ID(N'dbo.ChanDoan',        N'U') IS NOT NULL DROP TABLE dbo.ChanDoan;
IF OBJECT_ID(N'dbo.BienPhap',        N'U') IS NOT NULL DROP TABLE dbo.BienPhap;
IF OBJECT_ID(N'dbo.Benh',            N'U') IS NOT NULL DROP TABLE dbo.Benh;
IF OBJECT_ID(N'dbo.PhienBanMoHinh',  N'U') IS NOT NULL DROP TABLE dbo.PhienBanMoHinh;
IF OBJECT_ID(N'dbo.NguoiDung',       N'U') IS NOT NULL DROP TABLE dbo.NguoiDung;
GO

--=====================================================================
-- 1. NguoiDung - tài khoản người dùng
--=====================================================================

CREATE TABLE dbo.NguoiDung (
    user_id        INT IDENTITY(1,1) NOT NULL,
    full_name      NVARCHAR(100)     NOT NULL,
    email          NVARCHAR(255)     NOT NULL,
    password_hash  NVARCHAR(255)     NOT NULL,
    [role]         NVARCHAR(20)      NOT NULL
        CONSTRAINT DF_NguoiDung_role DEFAULT N'User',
    created_at     DATETIME2(0)      NOT NULL
        CONSTRAINT DF_NguoiDung_created_at DEFAULT SYSDATETIME(),
    is_active      BIT               NOT NULL
        CONSTRAINT DF_NguoiDung_is_active DEFAULT 1,

    CONSTRAINT PK_NguoiDung PRIMARY KEY (user_id),
    CONSTRAINT UQ_NguoiDung_email UNIQUE (email),
    CONSTRAINT CK_NguoiDung_role CHECK ([role] IN (N'Admin', N'User'))
);
GO

--=====================================================================
-- 2. PhienBanMoHinh - các phiên bản model AI
--=====================================================================

CREATE TABLE dbo.PhienBanMoHinh (
    model_id    INT IDENTITY(1,1) NOT NULL,
    model_name  NVARCHAR(100)     NOT NULL,
    version     NVARCHAR(30)      NOT NULL,
    model_path  NVARCHAR(500)     NOT NULL,
    created_at  DATETIME2(0)      NOT NULL
        CONSTRAINT DF_PhienBanMoHinh_created_at DEFAULT SYSDATETIME(),
    accuracy    FLOAT             NULL,
    f1_score    FLOAT             NULL,
    is_active   BIT               NOT NULL
        CONSTRAINT DF_PhienBanMoHinh_is_active DEFAULT 0,

    CONSTRAINT PK_PhienBanMoHinh PRIMARY KEY (model_id),
    CONSTRAINT UQ_PhienBanMoHinh_name_ver UNIQUE (model_name, version),
    CONSTRAINT CK_PhienBanMoHinh_accuracy
        CHECK (accuracy IS NULL OR accuracy BETWEEN 0 AND 1),
    CONSTRAINT CK_PhienBanMoHinh_f1_score
        CHECK (f1_score IS NULL OR f1_score BETWEEN 0 AND 1)
);
GO

--=====================================================================
-- 3. Benh - danh mục bệnh
--=====================================================================

CREATE TABLE dbo.Benh (
    disease_id    INT IDENTITY(1,1) NOT NULL,
    disease_name  NVARCHAR(150)     NOT NULL,
    class_key     NVARCHAR(50)      NULL,      -- khớp tên lớp trong class_names.json của model
    symptoms      NVARCHAR(MAX)     NULL,
    description   NVARCHAR(MAX)     NULL,

    CONSTRAINT PK_Benh PRIMARY KEY (disease_id),
    CONSTRAINT UQ_Benh_disease_name UNIQUE (disease_name)
);
GO

-- Duy nhất khi có giá trị, cho phép nhiều dòng NULL (bệnh thêm tay không gắn với lớp nào của model)
CREATE UNIQUE INDEX UX_Benh_class_key
    ON dbo.Benh (class_key) WHERE class_key IS NOT NULL;
GO
GO

--=====================================================================
-- 4. BienPhap - biện pháp xử lý và phòng ngừa
--=====================================================================

CREATE TABLE dbo.BienPhap (
    treatment_id    INT IDENTITY(1,1) NOT NULL,
    disease_id      INT               NOT NULL,
    treatment_name  NVARCHAR(200)     NOT NULL,
    treatment_type  NVARCHAR(30)      NULL,
    description     NVARCHAR(MAX)     NULL,
    prevention      NVARCHAR(MAX)     NULL,

    CONSTRAINT PK_BienPhap PRIMARY KEY (treatment_id),
    CONSTRAINT FK_BienPhap_Benh
        FOREIGN KEY (disease_id) REFERENCES dbo.Benh (disease_id),
    CONSTRAINT CK_BienPhap_type
        CHECK (
            treatment_type IS NULL
            OR treatment_type IN (N'Hóa học', N'Sinh học', N'Canh tác')
        )
);
GO

--=====================================================================
-- 5. ChanDoan - mỗi dòng là một lần chẩn đoán trên một ảnh
--=====================================================================

CREATE TABLE dbo.ChanDoan (
    diagnosis_id        INT IDENTITY(1,1) NOT NULL,
    user_id             INT               NOT NULL,
    model_id            INT               NOT NULL,
    image_path          NVARCHAR(500)     NOT NULL,
    diagnosis_date      DATETIME2(0)      NOT NULL
        CONSTRAINT DF_ChanDoan_diagnosis_date DEFAULT SYSDATETIME(),
    status              NVARCHAR(20)      NOT NULL
        CONSTRAINT DF_ChanDoan_status DEFAULT N'Pending',
    is_uncertain        BIT               NOT NULL
        CONSTRAINT DF_ChanDoan_is_uncertain DEFAULT 0,
    processing_time_ms  INT               NULL,
    is_correct          BIT               NULL,
    actual_disease_id   INT               NULL,

    CONSTRAINT PK_ChanDoan PRIMARY KEY (diagnosis_id),

    CONSTRAINT FK_ChanDoan_NguoiDung
        FOREIGN KEY (user_id) REFERENCES dbo.NguoiDung (user_id),

    CONSTRAINT FK_ChanDoan_PhienBanMoHinh
        FOREIGN KEY (model_id) REFERENCES dbo.PhienBanMoHinh (model_id),

    CONSTRAINT FK_ChanDoan_Benh_ThucTe
        FOREIGN KEY (actual_disease_id) REFERENCES dbo.Benh (disease_id),

    CONSTRAINT CK_ChanDoan_status
        CHECK (status IN (N'Pending', N'Completed', N'Failed')),

    CONSTRAINT CK_ChanDoan_processing
        CHECK (processing_time_ms IS NULL OR processing_time_ms >= 0)
);
GO

--=====================================================================
-- 6. KetQuaChanDoan - tối đa 3 bệnh có xác suất cao nhất
--=====================================================================

CREATE TABLE dbo.KetQuaChanDoan (
    result_id         INT IDENTITY(1,1) NOT NULL,
    diagnosis_id      INT               NOT NULL,
    disease_id        INT               NOT NULL,
    rank_no           TINYINT           NOT NULL,
    confidence_score  DECIMAL(5,4)      NOT NULL,

    CONSTRAINT PK_KetQuaChanDoan PRIMARY KEY (result_id),

    CONSTRAINT FK_KetQuaChanDoan_ChanDoan
        FOREIGN KEY (diagnosis_id)
        REFERENCES dbo.ChanDoan (diagnosis_id)
        ON DELETE CASCADE,

    CONSTRAINT FK_KetQuaChanDoan_Benh
        FOREIGN KEY (disease_id) REFERENCES dbo.Benh (disease_id),

    CONSTRAINT UQ_KetQuaChanDoan_rank
        UNIQUE (diagnosis_id, rank_no),

    CONSTRAINT UQ_KetQuaChanDoan_disease
        UNIQUE (diagnosis_id, disease_id),

    CONSTRAINT CK_KetQuaChanDoan_rank_no
        CHECK (rank_no IN (1, 2, 3)),

    CONSTRAINT CK_KetQuaChanDoan_confidence
        CHECK (confidence_score BETWEEN 0 AND 1)
);
GO

--=====================================================================
-- 7. DuLieuHuanLuyen - mỗi phiên bản mô hình có một bộ dữ liệu riêng (quan hệ 1-1)
--=====================================================================

CREATE TABLE dbo.DuLieuHuanLuyen (
    id           INT IDENTITY(1,1) NOT NULL,
    model_id     INT               NOT NULL,
    file_size    BIGINT            NULL,
    file_format  VARCHAR(10)       NOT NULL,
    source       NVARCHAR(255)     NULL,
    description  NVARCHAR(255)     NULL,
    created_at   DATETIME2(0)      NOT NULL
        CONSTRAINT DF_DuLieuHuanLuyen_created_at DEFAULT SYSDATETIME(),

    CONSTRAINT PK_DuLieuHuanLuyen PRIMARY KEY (id),

    -- Mỗi phiên bản mô hình chỉ có đúng tối đa một bộ dữ liệu huấn luyện.
    CONSTRAINT UQ_DuLieuHuanLuyen_model_id UNIQUE (model_id),

    CONSTRAINT FK_DuLieuHuanLuyen_PhienBanMoHinh
        FOREIGN KEY (model_id) REFERENCES dbo.PhienBanMoHinh (model_id),

    CONSTRAINT CK_DuLieuHuanLuyen_file_size
        CHECK (file_size IS NULL OR file_size >= 0)
);
GO

--=====================================================================
-- 8. Chỉ mục cho khóa ngoại và truy vấn thường dùng
--=====================================================================

CREATE INDEX IX_BienPhap_disease_id
    ON dbo.BienPhap (disease_id);

CREATE INDEX IX_ChanDoan_user_date
    ON dbo.ChanDoan (user_id, diagnosis_date DESC);

CREATE INDEX IX_ChanDoan_model_id
    ON dbo.ChanDoan (model_id);

CREATE INDEX IX_ChanDoan_actual_disease_id
    ON dbo.ChanDoan (actual_disease_id);

CREATE INDEX IX_KetQuaChanDoan_disease_id
    ON dbo.KetQuaChanDoan (disease_id);

-- model_id đã có UNIQUE nên SQL Server đã tự tạo chỉ mục duy nhất cho quan hệ 1-1.

GO

--=====================================================================
-- 9. Dữ liệu mẫu cho bảng Benh
--=====================================================================

IF NOT EXISTS (SELECT 1 FROM dbo.Benh)
BEGIN
    INSERT INTO dbo.Benh (disease_name, class_key) VALUES
    (N'Bệnh thán thư', 'anthracnose'),
    (N'Bệnh loét', 'canker_disease'),
    (N'Bệnh thối do nấm', 'fruit_rot'),
    (N'Rệp sáp', 'mealybug_infestation'),
    (N'Bệnh nấm hồng', 'pink_disease'),
    (N'Bệnh nấm bồ hóng', 'sooty_mold'),
    (N'Bệnh khô chết', 'stem_blight'),
    (N'Bệnh nứt thân xì mủ', 'stem_cracking_gummosis'),
    (N'Bọ trĩ', 'thrips_disease'),
    (N'Bệnh vàng lá', 'yellow_leaf'),
    (N'Lá khỏe mạnh', 'healthy_leaf'),
    (N'Bệnh đốm rong', 'algal_leaf_spot'),
    (N'Bệnh đốm do nấm Phomopsis', 'phomopsis_leaf_spot'),
    (N'Bệnh cháy lá (chưa rõ tác nhân)', 'leaf_blight'),
    (N'Bệnh cháy lá do nấm Rhizoctonia', 'leaf_rhizoctonia'),
    (N'Rầy nhảy (Allocaridara)', 'allocaridara_attack');
END
GO

--=====================================================================
-- 10. Tài khoản mẫu
--=====================================================================

INSERT INTO dbo.NguoiDung
    (full_name, email, password_hash, [role])
VALUES
    (
        N'ĐẾ THÍCH THIÊN',
        N'admin@phucdeptrai.vn',
        N'$2b$12$QarTxplox7geee53p/yBce4hWTaOsIJsQBm8aAdH8GUCmQg6CFJUK',
        N'Admin'
    ),
    (
        N'NÔ LỆ SỐ 1',
        N'user@phucdeptrai.vn',
        N'$2b$12$QarTxplox7geee53p/yBce4hWTaOsIJsQBm8aAdH8GUCmQg6CFJUK',
        N'User'
    );
GO
SELECT disease_id, disease_name, class_key FROM dbo.Benh ORDER BY disease_id;